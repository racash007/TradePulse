"""
SignalGenerator
- Runs FVGOrderBlocks and SonarlabOrderBlocks on an input CSV (or DataFrame)
- Produces Signal objects with a signalStrength according to rules:
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
from typing import List
import pandas as pd

from app.utility.file_util import get_security_name, read_csv_into_df
from app.strategy.fvgorderblocks import FVGOrderBlocks
from app.strategy.sonarlaplaceorderblocks import SonarlaplaceOrderBlocks
from app.model.signal import Signal
from app.agent.signal_processor import (
    normalize_raw_signal,
    is_buy_signal,
    run_all_strategies,
    collect_signals_from_strategies
)
from app.agent.signal_strength import (
    calculate_signal_strength,
    check_fvg_inclusion,
    check_sonar_inclusion
)

# Module-level singleton instance
_instance = None


def get_signal_generator(dark_alpha_threshold: float = 0.4) -> 'SignalGenerator':
    """
    Get or create a singleton SignalGenerator instance.

    Args:
        dark_alpha_threshold: Only used when creating the instance for the first time.

    Returns:
        The singleton SignalGenerator instance.
    """
    global _instance
    if _instance is None:
        _instance = SignalGenerator(dark_alpha_threshold)
    return _instance


def reset_signal_generator():
    """Reset the singleton instance. Useful for testing."""
    global _instance
    _instance = None


class SignalGenerator:
    def __init__(self, dark_alpha_threshold: float = 0.4):
        """dark_alpha_threshold: alpha >= this value is considered dark block"""
        self.dark_alpha_threshold = dark_alpha_threshold

    def generate_from_file(self, df: pd.DataFrame, file_name: str) -> List[Signal]:
        """Main entry: generates signals from DataFrame.
        Returns list of Signal objects with computed signalStrength."""

        # Create fresh strategy instances for each call (thread-safe)
        self.fvg = FVGOrderBlocks()
        self.sonar = SonarlaplaceOrderBlocks()
        self.strategies = [self.fvg, self.sonar]

        # Run all strategies
        run_all_strategies(self.strategies, df)

        # Collect raw signals from all strategies
        raw_signals = collect_signals_from_strategies(self.strategies)

        # Process and enhance signals
        enhanced = self._process_raw_signals(raw_signals, df, file_name)

        return enhanced

    def _process_raw_signals(self, raw_signals: List, df: pd.DataFrame, file_name: str) -> List[Signal]:
        """Process raw signals and create enhanced Signal objects."""
        enhanced = []
        seen = set()

        for s in raw_signals:
            # Normalize signal
            normalized = normalize_raw_signal(s)
            if normalized is None:
                continue

            idx = normalized['idx']
            price = normalized['price']
            typ = normalized['typ']
            color = normalized['color']
            source = normalized['source']

            # Deduplicate
            key = (idx, round(price, 6), str(typ))
            if key in seen:
                continue
            seen.add(key)

            # Determine signal direction
            is_buy = is_buy_signal(typ)

            # Check box inclusions
            inside_fvg, fvg_alpha = check_fvg_inclusion(idx, price, is_buy, self.fvg)
            inside_sonar = check_sonar_inclusion(idx, price, is_buy, self.sonar)

            # Calculate signal strength
            signalStrength = calculate_signal_strength(
                inside_fvg, inside_sonar, fvg_alpha, self.dark_alpha_threshold
            )

            # Map index to date
            date_val = self._get_date_from_index(df, idx)

            # Create enhanced signal
            enhanced.append(Signal(
                index=idx,
                price=price,
                date=date_val,
                type=typ if typ is not None else '',
                symbol=get_security_name(file_name),
                color=color,
                inside_fvg=inside_fvg,
                inside_sonar=inside_sonar,
                fvg_alpha=fvg_alpha,
                signalStrength=signalStrength,
                source_strategy=[source]
            ))

        return enhanced

    def _get_date_from_index(self, df: pd.DataFrame, idx: int):
        """Get date value from DataFrame index."""
        try:
            if hasattr(df, 'index') and len(df.index) > idx:
                return df.index[int(idx)]
        except Exception:
            pass
        return None

    def to_dataframe(self, enhanced_signals: List[Signal]) -> pd.DataFrame:
        """Convert enhanced signals list to a pandas DataFrame for UI or export."""
        rows = []
        for s in enhanced_signals:
            rows.append({
                'date': s.date,
                'index': s.index,
                'price': s.price,
                'type': self._normalize_signal_type(s.type),
                'symbol': s.symbol,
                'color': s.color,
                'fvg_alpha': s.fvg_alpha,
                'signalStrength': s.signalStrength,
                'source_strategy': ','.join(s.source_strategy) if isinstance(s.source_strategy, list) else s.source_strategy
            })

        # Always ensure the resulting DataFrame has the expected columns even when empty
        columns = ['date', 'index', 'price', 'type', 'symbol', 'color', 'fvg_alpha', 'signalStrength', 'source_strategy']
        if rows:
            df = pd.DataFrame(rows)
        else:
            df = pd.DataFrame(columns=columns)

        # Normalize date column to datetime dtype if present
        if 'date' in df.columns:
            try:
                df['date'] = pd.to_datetime(df['date'])
            except Exception:
                # ensure dtype exists even if parsing fails
                df['date'] = pd.Series([], dtype='datetime64[ns]')

        return df

    def _normalize_signal_type(self, signal_type) -> str:
        """Normalize signal type to 'buy'/'sell' for UI."""
        if isinstance(signal_type, str):
            lower_type = signal_type.lower()
            if 'bull' in lower_type or 'buy' in lower_type:
                return 'buy'
            elif 'bear' in lower_type or 'sell' in lower_type:
                return 'sell'
        return signal_type

    def generate_df(self, csv_input: str) -> pd.DataFrame:
        """Run generation and return a DataFrame of enhanced signals."""
        df = read_csv_into_df(csv_input)
        enhanced = self.generate_from_file(df, csv_input)
        return self.to_dataframe(enhanced)