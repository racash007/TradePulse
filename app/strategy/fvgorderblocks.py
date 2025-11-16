# -------------------------
# FVG Order Blocks [BigBeluga] (full logic)
# -------------------------
import math
from typing import List

import matplotlib.pyplot as plt
import pandas as pd
from pandas import DataFrame

from app.model.box import Box, BoxType
from app.model.signal import Signal
from app.model.SignalType import SignalType
from app.strategy.strategy import Strategy
from app.utility.plot_utils import draw_candlesticks, draw_boxes, draw_signals, setup_chart_axes
from app.utility.utility import atr_series, clamp


class FVGOrderBlocks(Strategy):
    """
    Python translation of the Pine "FVG Order Blocks [BigBeluga]" indicator.
    Inputs/Defaults mirrored from Pine:
        loockback = 2000
        filter = 0.5
        show_imb = True
        box_amount = 6
        show_broken = False
        show_signal = False
        col_bull = #14be94
        col_bear = rgb(194,25,25) -> #C21919
    """

    def __init__(self,
                 filter_gap: float = 0.5,
                 show_imb: bool = True,
                 box_amount: int = 6,
                 show_broken: bool = False,
                 show_signal: bool = False,
                 col_bull: str = "#14be94",
                 col_bear: str = "#C21919",
                 lookback: int = 2000):
        self.filter_gap = filter_gap
        self.show_imb = show_imb
        self.box_amount = box_amount
        self.show_broken = show_broken
        self.show_signal = show_signal
        self.col_bull = col_bull
        self.col_bear = col_bear
        self.lookback = lookback
        self.window_size = 2000

        # Storage for boxes and signals
        self.bull_boxes: List[Box] = []
        self.bear_boxes: List[Box] = []
        self.temp_boxes: List[Box] = []
        self.signals: List[Signal] = []

    def run(self, df: pd.DataFrame):
        """
        df: DataFrame with columns ['Open','High','Low','Close'] indexed by date
        After run, self.bull_boxes, self.bear_boxes and self.signals will be populated.
        """
        # Reset state for new run
        self.bull_boxes = []
        self.bear_boxes = []
        self.temp_boxes = []
        self.signals = []

        n = len(df)
        if n == 0:
            return

        # ATR replicating ta.atr(200)
        atr = atr_series(df, period=200)

        # Filters
        filt_up = (df['Low'] - df['High'].shift(2)) / df['Low'] * 100
        filt_dn = (df['Low'].shift(2) - df['High']) / df['Low'].shift(2) * 100

        max_up = filt_up.rolling(self.window_size, min_periods=1).max()
        max_dn = filt_dn.rolling(self.window_size, min_periods=1).max()

        # Iterate bars in chronological order
        for idx in range(n):
            if (n - 1 - idx) < self.lookback:
                isBull_gap, isBear_gap = self._detect_gaps(df, filt_up, filt_dn, idx)
            else:
                isBull_gap = False
                isBear_gap = False

            # Bullish Imbalance
            if isBull_gap:
                self._create_temp_bullish_box(df, filt_up, idx, n)
                self._create_bullish_box(atr, df, filt_up, idx, max_up, n)

            # Bearish Imbalance
            if isBear_gap:
                self._create_temp_bearish_box(df, filt_dn, idx, n)
                self._create_bearish_box(atr, df, filt_dn, idx, max_dn, n)

            # Handle broken levels & signals
            self._process_bull_boxes(df, idx, isBull_gap)
            self._remove_nested_bull_boxes()
            self._process_bear_boxes(df, idx, isBear_gap)
            self._remove_nested_bear_boxes()
            self._limit_box_count()

        # Extend boxes to the right
        self._extend_boxes(n)

    def _detect_gaps(self, df: DataFrame, filt_up: pd.Series, filt_dn: pd.Series, idx: int) -> tuple:
        """Detect bullish and bearish gaps at the given index."""
        if idx >= 2:
            isBull_gap = (
                df['High'].shift(2).iat[idx] < df['Low'].iat[idx]
                and df['High'].shift(2).iat[idx] < df['High'].shift(1).iat[idx]
                and df['Low'].shift(2).iat[idx] < df['Low'].iat[idx]
                and (filt_up.iat[idx] > self.filter_gap)
            )
            isBear_gap = (
                df['Low'].shift(2).iat[idx] > df['High'].iat[idx]
                and df['Low'].shift(2).iat[idx] > df['Low'].shift(1).iat[idx]
                and df['High'].shift(2).iat[idx] > df['High'].iat[idx]
                and (filt_dn.iat[idx] > self.filter_gap)
            )
        else:
            isBull_gap = False
            isBear_gap = False
        return isBull_gap, isBear_gap

    def _create_temp_bullish_box(self, df: DataFrame, filt_up: pd.Series, idx: int, n: int):
        """Create temporary box for bullish imbalance."""
        if not self.show_imb:
            return

        left = idx - 1
        right = idx + 5
        top_v = df['Low'].iat[idx]
        bottom_v = df['High'].shift(2).iat[idx]
        top_normal = max(top_v, bottom_v)
        bottom_normal = min(top_v, bottom_v)

        self.temp_boxes.append(Box(
            left=left,
            right=min(right, n - 1),
            top=top_normal,
            bottom=bottom_normal,
            box_type=BoxType.TEMP_BULL,
            percent=filt_up.iat[idx],
            alpha=0.12
        ))

    def _create_bullish_box(self, atr: pd.Series, df: DataFrame, filt_up: pd.Series,
                            idx: int, max_up: pd.Series, n: int):
        """Create permanent bullish box."""
        if idx >= 2 and not math.isnan(atr.iat[idx]):
            top_val = df['High'].shift(2).iat[idx]
            bottom_val = top_val - atr.iat[idx]
            percent_val = filt_up.iat[idx]
            p_norm = percent_val / (
                max_up.iat[idx] if (not math.isnan(max_up.iat[idx]) and max_up.iat[idx] != 0) else 1.0
            )
            alpha = clamp(0.15 + 0.5 * (p_norm if p_norm > 0 else 0), 0.06, 0.7)

            self.bull_boxes.append(Box(
                left=idx - 1,
                right=n - 1,
                top=top_val,
                bottom=bottom_val,
                box_type=BoxType.BULL,
                percent=percent_val,
                alpha=alpha,
                border_color=self.col_bull,
                bg_color=self.col_bull,
                broken=False,
                border_width=1
            ))

    def _create_temp_bearish_box(self, df: DataFrame, filt_dn: pd.Series, idx: int, n: int):
        """Create temporary box for bearish imbalance."""
        if not self.show_imb:
            return

        left = idx - 1
        right = idx + 5
        top_v = df['High'].iat[idx]
        bottom_v = df['Low'].shift(2).iat[idx]
        top_normal = max(top_v, bottom_v)
        bottom_normal = min(top_v, bottom_v)

        self.temp_boxes.append(Box(
            left=left,
            right=min(right, n - 1),
            top=top_normal,
            bottom=bottom_normal,
            box_type=BoxType.TEMP_BEAR,
            percent=filt_dn.iat[idx],
            alpha=0.12
        ))

    def _create_bearish_box(self, atr: pd.Series, df: DataFrame, filt_dn: pd.Series,
                            idx: int, max_dn: pd.Series, n: int):
        """Create permanent bearish box."""
        if idx >= 2 and not math.isnan(atr.iat[idx]):
            top_val = df['Low'].shift(2).iat[idx] + atr.iat[idx]
            bottom_val = df['Low'].shift(2).iat[idx]
            percent_val = filt_dn.iat[idx]
            p_norm = percent_val / (
                max_dn.iat[idx] if (not math.isnan(max_dn.iat[idx]) and max_dn.iat[idx] != 0) else 1.0
            )
            alpha = clamp(0.15 + 0.5 * (p_norm if p_norm > 0 else 0), 0.06, 0.7)

            self.bear_boxes.append(Box(
                left=idx - 1,
                right=n - 1,
                top=top_val,
                bottom=bottom_val,
                box_type=BoxType.BEAR,
                percent=percent_val,
                alpha=alpha,
                border_color=self.col_bear,
                bg_color=self.col_bear,
                broken=False,
                border_width=1
            ))

    def _process_bull_boxes(self, df: DataFrame, idx: int, isBull_gap: bool):
        """Process bull boxes for broken detection and signals."""
        to_delete = set()

        for bi, box in enumerate(self.bull_boxes):
            # Check if broken
            if df['High'].iat[idx] < box.bottom:
                box.border_width = 0
                box.bg_color = "#E6E6E6"
                box.broken = True
                if not self.show_broken:
                    to_delete.add(bi)

            # Signal condition
            if self.show_signal and idx >= 1:
                if (df['Low'].iat[idx] > box.top >= df['Low'].shift(1).iat[idx] and not isBull_gap):
                    self.signals.append(Signal(
                        index=idx - 1,
                        price=df['Low'].shift(1).iat[idx],
                        date=None,
                        type=SignalType.BUY,
                        symbol="\ufe3d",
                        color=self.col_bull,
                        inside_fvg=True,
                        inside_sonar=False,
                        fvg_alpha=box.alpha,
                        signalStrength=0,
                        source_strategy=['FVGOrderBlocks']
                    ))

        # Remove broken boxes
        if to_delete:
            self.bull_boxes = [b for i, b in enumerate(self.bull_boxes) if i not in to_delete]

    def _process_bear_boxes(self, df: DataFrame, idx: int, isBear_gap: bool):
        """Process bear boxes for broken detection and signals."""
        to_delete = set()

        for bi, box in enumerate(self.bear_boxes):
            # Check if broken
            if df['Low'].iat[idx] > box.top:
                box.border_width = 0
                box.bg_color = "#E6E6E6"
                box.broken = True
                if not self.show_broken:
                    to_delete.add(bi)

            # Signal condition
            if self.show_signal and idx >= 1:
                if (df['High'].iat[idx] < box.bottom <= df['High'].shift(1).iat[idx] and not isBear_gap):
                    self.signals.append(Signal(
                        index=idx - 1,
                        price=df['High'].shift(1).iat[idx],
                        date=None,
                        type=SignalType.SELL,
                        symbol="\ufe40",
                        color=self.col_bear,
                        inside_fvg=True,
                        inside_sonar=False,
                        fvg_alpha=box.alpha,
                        signalStrength=0,
                        source_strategy=['FVGOrderBlocks']
                    ))

        # Remove broken boxes
        if to_delete:
            self.bear_boxes = [b for i, b in enumerate(self.bear_boxes) if i not in to_delete]

    def _remove_nested_bull_boxes(self):
        """Remove nested bull boxes."""
        remove_indices = set()
        for i_outer, box in enumerate(self.bull_boxes):
            for i_inner, box1 in enumerate(self.bull_boxes):
                if i_outer == i_inner:
                    continue
                if (box1.top < box.top) and (box1.top > box.bottom):
                    remove_indices.add(i_outer)
                    break

        if remove_indices:
            self.bull_boxes = [b for i, b in enumerate(self.bull_boxes) if i not in remove_indices]

    def _remove_nested_bear_boxes(self):
        """Remove nested bear boxes."""
        remove_indices = set()
        for i_outer, box in enumerate(self.bear_boxes):
            for i_inner, box1 in enumerate(self.bear_boxes):
                if i_outer == i_inner:
                    continue
                if (box1.top < box.top) and (box1.top > box.bottom):
                    remove_indices.add(i_outer)
                    break

        if remove_indices:
            self.bear_boxes = [b for i, b in enumerate(self.bear_boxes) if i not in remove_indices]

    def _limit_box_count(self):
        """Limit the number of boxes to box_amount."""
        while len(self.bull_boxes) >= self.box_amount:
            self.bull_boxes.pop(0)
        while len(self.bear_boxes) >= self.box_amount:
            self.bear_boxes.pop(0)

    def _extend_boxes(self, n: int):
        """Extend boxes to the right edge."""
        right_ext = n - 1 + 15
        for b in self.bull_boxes:
            b.right = right_ext
        for b in self.bear_boxes:
            b.right = right_ext
        for t in self.temp_boxes:
            t.right = min(t.right, n - 1)

    def get_signals(self) -> List[Signal]:
        """Return the list of signals generated by the strategy."""
        return self.signals

    def plot(self, df: pd.DataFrame, title: str = "FVG Order Blocks [BigBeluga]", ax=None):
        """Draw candles and boxes using matplotlib."""
        dates = list(df.index)

        if ax is None:
            fig, ax = plt.subplots(figsize=(14, 7))

        # Draw candlesticks
        draw_candlesticks(ax, df)

        # Draw boxes
        draw_boxes(ax, self.bull_boxes, dates)
        draw_boxes(ax, self.bear_boxes, dates)

        # Draw temp boxes with light color
        for t in self.temp_boxes:
            if t.left < 0 or t.right < 0:
                continue
            from matplotlib.patches import Rectangle
            import matplotlib.dates as mdates
            left = mdates.date2num(dates[max(0, t.left)])
            right = mdates.date2num(dates[min(len(dates) - 1, t.right)])
            rect = Rectangle(
                (left, t.bottom),
                right - left,
                t.top - t.bottom,
                facecolor=(0.7, 0.7, 0.95, t.alpha),
                edgecolor='none',
                zorder=0
            )
            ax.add_patch(rect)
            if t.percent is not None:
                try:
                    pct_text = f"{t.percent:.2f}%"
                    ax.text(
                        left + (right - left) * 0.02,
                        (t.top + t.bottom) / 2,
                        pct_text,
                        verticalalignment='center',
                        horizontalalignment='left',
                        fontsize=8,
                        color='black',
                        zorder=2
                    )
                except:
                    pass

        # Draw signals
        draw_signals(ax, self.signals, dates, self.col_bull, self.col_bear)

        # Setup axes
        setup_chart_axes(ax, title)