"""
SignalGenerator
- Runs FVGOrderBlocks and SonarlabOrderBlocks on an input CSV (or DataFrame)
- Produces EnhancedSignal objects with a signalStrength according to rules:
  * buy inside light-green FVG block -> signalStrength = 1
  * buy inside dark-green FVG block  -> signalStrength = 2
  * buy inside light-green FVG block AND Sonarlab block -> 3
  * buy inside dark-green FVG block AND Sonarlab block  -> 4
  (same logic for sell signals, using FVG bear boxes and Sonarlab short boxes)

Assumptions:
- "Dark" FVG boxes are those with alpha >= 0.4 (alpha computed by FVG implementation)
- CSV file can be either a full path to a CSV or a short filter string used by utility.load_data
- Handles Signal objects and dict-like signals produced by the strategies
"""
from dataclasses import dataclass
from typing import Optional, List
import os
import pandas as pd

# resilient imports (package vs script)
try:
    from app.strategy.fvgorderblocks import FVGOrderBlocks
    from app.strategy.sonarlaborderblocks import SonarlabOrderBlocks
    from app.strategy.signal import Signal
    from app.utility.utility import load_data
except Exception:
    # dynamic imports to avoid static-analysis warnings; modules expected when running as script
    import importlib
    FVGOrderBlocks = importlib.import_module('strategy.fvgorderblocks').FVGOrderBlocks
    SonarlabOrderBlocks = importlib.import_module('strategy.sonarlaborderblocks').SonarlabOrderBlocks
    Signal = importlib.import_module('strategy.signal').Signal
    load_data = importlib.import_module('utility.utility').load_data


@dataclass
class EnhancedSignal:
    index: int
    price: float
    date: Optional[pd.Timestamp]
    type: str  # 'buy'/'sell' or 'bullish'/'bearish'
    symbol: Optional[str]
    color: Optional[str]
    inside_fvg: bool
    inside_sonar: bool
    fvg_alpha: Optional[float]
    signalStrength: int
    source_strategy: List[str]


class SignalGenerator:
    def __init__(self, dark_alpha_threshold: float = 0.4):
        """dark_alpha_threshold: alpha >= this value is considered dark block"""
        self.dark_alpha_threshold = dark_alpha_threshold

    def _read_csv_into_df(self, csv_input: str) -> pd.DataFrame:
        """
        Accepts either a path to a CSV file or a filter string for utility.load_data.
        Returns a DataFrame with Date parsed as index and columns Open/High/Low/Close numeric.
        """
        # If input looks like an existing file path, read it directly
        if os.path.isfile(csv_input):
            df = pd.read_csv(csv_input)
        else:
            # fallback to load_data(filter)
            df = load_data(csv_input)
            return df

        # try to normalize column names similar to utility.load_data
        cols = list(df.columns)
        # common variations
        mapping = {}
        lower = [c.lower() for c in cols]
        if 'date' in lower:
            mapping[cols[lower.index('date')]] = 'Date'
        if 'close price' in lower:
            mapping[cols[lower.index('close price')]] = 'Close'
        if 'open price' in lower:
            mapping[cols[lower.index('open price')]] = 'Open'
        if 'high price' in lower:
            mapping[cols[lower.index('high price')]] = 'High'
        if 'low price' in lower:
            mapping[cols[lower.index('low price')]] = 'Low'
        # fallback common names
        if 'close' in lower and 'Close' not in mapping.values():
            mapping[cols[lower.index('close')]] = 'Close'
        if 'open' in lower and 'Open' not in mapping.values():
            mapping[cols[lower.index('open')]] = 'Open'
        if 'high' in lower and 'High' not in mapping.values():
            mapping[cols[lower.index('high')]] = 'High'
        if 'low' in lower and 'Low' not in mapping.values():
            mapping[cols[lower.index('low')]] = 'Low'

        if mapping:
            df = df.rename(columns=mapping)

        # Ensure numeric types and remove commas
        for col in ['Open', 'High', 'Low', 'Close']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce')
            else:
                raise ValueError(f"Required column '{col}' not found in CSV")

        # parse Date
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.set_index('Date')

        return df

    def _point_in_box(self, idx: int, price: float, box: dict) -> bool:
        # index inside left..right (inclusive) and price between bottom and top (inclusive)
        if box is None:
            return False
        left = box.get('left', -9999)
        right = box.get('right', 9999)
        top = box.get('top')
        bottom = box.get('bottom')
        try:
            idx_ok = (idx >= left) and (idx <= right)
            price_ok = (top is not None and bottom is not None and price <= top and price >= bottom)
            return idx_ok and price_ok
        except Exception:
            return False

    def generate_from_file(self, csv_input: str) -> List[EnhancedSignal]:
        """Main entry: csv_input can be a full path or a filter string for load_data
        Returns list of EnhancedSignal objects with computed signalStrength."""
        df = None
        if isinstance(csv_input, str):
            df = self._read_csv_into_df(csv_input)
        elif isinstance(csv_input, pd.DataFrame):
            df = csv_input
        else:
            raise ValueError("csv_input must be a file path, filter string, or DataFrame")

        # run strategies
        fvg = FVGOrderBlocks()
        fvg.run(df)
        sonar = SonarlabOrderBlocks()
        sonar.run(df)

        fvg_boxes = fvg.bull_boxes + fvg.bear_boxes
        sonar_boxes = sonar.long_boxes + sonar.short_boxes

        # collect raw signals from both strategies
        raw_signals = []
        try:
            raw_signals.extend(fvg.get_signals() or [])
        except Exception:
            pass
        try:
            raw_signals.extend(sonar.get_signals() or [])
        except Exception:
            pass

        enhanced = []
        seen = set()
        for s in raw_signals:
            # normalize
            if hasattr(s, 'index'):
                idx = int(s.index)
                price = float(s.price) if s.price is not None else None
                typ = getattr(s, 'type', None)
                symbol = getattr(s, 'symbol', None)
                color = getattr(s, 'color', None)
                source = 'SignalObject'
            elif isinstance(s, dict):
                idx = int(s.get('index')) if s.get('index') is not None else None
                price = float(s.get('price')) if s.get('price') is not None else None
                typ = s.get('type') or s.get('signal')
                symbol = s.get('symbol')
                color = s.get('color')
                source = 'SignalDict'
            else:
                continue
            if idx is None or price is None:
                continue

            key = (idx, round(price, 6), str(typ))
            if key in seen:
                # avoid duplicates
                continue
            seen.add(key)

            typ_str = str(typ).lower() if typ is not None else ''
            is_buy = 'bull' in typ_str or 'buy' in typ_str
            is_sell = 'bear' in typ_str or 'sell' in typ_str

            # Determine FVG inclusion and alpha
            inside_fvg = False
            fvg_alpha = None
            for box in fvg.bull_boxes if is_buy else fvg.bear_boxes:
                if self._point_in_box(idx, price, box):
                    inside_fvg = True
                    fvg_alpha = box.get('alpha', None)
                    break

            # Determine Sonar inclusion
            inside_sonar = False
            for box in (sonar.long_boxes if is_buy else sonar.short_boxes):
                if self._point_in_box(idx, price, box):
                    inside_sonar = True
                    break

            # Compute strength following mapping
            signalStrength = 0
            if inside_fvg and not inside_sonar:
                # only FVG
                if fvg_alpha is not None and fvg_alpha >= self.dark_alpha_threshold:
                    signalStrength = 2
                else:
                    signalStrength = 1
            elif inside_fvg and inside_sonar:
                # both
                if fvg_alpha is not None and fvg_alpha >= self.dark_alpha_threshold:
                    signalStrength = 4
                else:
                    signalStrength = 3
            elif inside_sonar and not inside_fvg:
                # sonar-only fallback (not specified): assign 1
                signalStrength = 1
            else:
                # neither inside -> 0 (weak/none)
                signalStrength = 0

            # map index -> date if df has a DatetimeIndex
            date_val = None
            try:
                if hasattr(df, 'index') and len(df.index) > idx:
                    date_val = df.index[int(idx)]
            except Exception:
                date_val = None

            enhanced.append(EnhancedSignal(
                index=idx,
                price=price,
                date=date_val,
                type=typ if typ is not None else '',
                symbol=symbol,
                color=color,
                inside_fvg=inside_fvg,
                inside_sonar=inside_sonar,
                fvg_alpha=fvg_alpha,
                signalStrength=signalStrength,
                source_strategy=[source]
            ))

        return enhanced

    def to_dataframe(self, enhanced_signals: List[EnhancedSignal]) -> pd.DataFrame:
        """Convert enhanced signals list to a pandas DataFrame for UI or export."""
        rows = []
        for s in enhanced_signals:
            rows.append({
                'date': s.date,
                'index': s.index,
                'price': s.price,
                # normalize signal type to 'buy'/'sell' for UI
                'type': ('buy' if (isinstance(s.type, str) and (
                            s.type.lower().find('bull') != -1 or s.type.lower().find('buy') != -1)) else ('sell' if (
                            isinstance(s.type, str) and (
                                s.type.lower().find('bear') != -1 or s.type.lower().find('sell') != -1)) else s.type)),
                'symbol': s.symbol,
                'color': s.color,
                'fvg_alpha': s.fvg_alpha,
                'signalStrength': s.signalStrength,
                'source_strategy': ','.join(s.source_strategy) if isinstance(s.source_strategy,
                                                                             list) else s.source_strategy
            })
        df = pd.DataFrame(rows)
        # try to normalize date column to pandas datetime (if present)
        if 'date' in df.columns:
            try:
                df['date'] = pd.to_datetime(df['date'], errors='ignore')
            except Exception:
                pass
        return df

    def generate_df(self, csv_input: str) -> pd.DataFrame:
        """Run generation and return a DataFrame of enhanced signals."""
        enhanced = self.generate_from_file(csv_input)
        return self.to_dataframe(enhanced)


if __name__ == '__main__':
    # quick manual smoke test for local developer: won't run in CI
    sg = SignalGenerator()
    try:
        signals = sg.generate_from_file('07-03-2025-TO-07-09-2025-ABB-EQ-N.csv')
        print('Found', len(signals), 'enhanced signals')
    except Exception as e:
        print('Smoke test error:', e)
