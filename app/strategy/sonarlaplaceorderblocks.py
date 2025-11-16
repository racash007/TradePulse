# -------------------------
# Sonarlab - Order Blocks (full logic)
# -------------------------
from typing import List
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from app.model.box import Box, BoxType
from app.model.signal import Signal
from app.model.SignalType import SignalType
from app.strategy.strategy import Strategy
from app.utility.plot_utils import draw_candlesticks, draw_boxes, draw_signals, setup_chart_axes


class SonarlaplaceOrderBlocks(Strategy):
    """
    Python translation of "Sonarlab - Order Blocks".
    Mirrors:
     - sensitivity (28 default) -> sens = sensitivity/100
     - OBMitigationType: "Close" or "Wick"
     - OBBullMitigation = Close[1] if Close else Low
     - OBBearMitigation = Close[1] if Close else High
     - pc = (open - open[4]) / open[4] * 100
     - ta.crossunder(pc, -sens) -> ob_created = True, cross_index := bar_index
     - ta.crossover(pc, sens) -> ob_created_bull = True, cross_index := bar_index
     - For creation, ensure gap from previously created OBs: cross_index - cross_index[1] > 5
     - loops offsets 4..15 to find first RED/GREEN candle to place OB
     - cleanup and alert rules replicated exactly
    """

    def __init__(self,
                 sensitivity: int = 28,
                 OBMitigationType: str = "Close",
                 col_bullish: str = "#5db49e",
                 col_bullish_ob: str = "#64C4AC",
                 col_bearish: str = "#4760bb",
                 col_bearish_ob: str = "#506CD3",
                 buy_alert: bool = True,
                 sell_alert: bool = True):
        self.sensitivity = sensitivity
        self.sens = sensitivity / 100.0
        self.OBMitigationType = OBMitigationType
        self.col_bullish = col_bullish
        self.col_bullish_ob = col_bullish_ob
        self.col_bearish = col_bearish
        self.col_bearish_ob = col_bearish_ob
        self.buy_alert = buy_alert
        self.sell_alert = sell_alert

        # Storage
        self.long_boxes: List[Box] = []
        self.short_boxes: List[Box] = []
        self.signals: List[Signal] = []

    def run(self, df: pd.DataFrame):
        """Run the strategy on the given DataFrame."""
        # Reset state for new run
        self.long_boxes = []
        self.short_boxes = []
        self.signals = []

        n = len(df)
        if n == 0:
            return

        # pc series
        pc = (df['Open'] - df['Open'].shift(4)) / df['Open'].shift(4) * 100

        # mitigation as series
        if self.OBMitigationType == "Close":
            OBBullMitigation = df['Close'].shift(1)
            OBBearMitigation = df['Close'].shift(1)
        else:
            OBBullMitigation = df['Low']
            OBBearMitigation = df['High']

        # State variables
        ob_created = False
        ob_created_bull = False

        # Iterate bars
        for idx in range(n):
            # Detect crossovers
            if idx >= 1:
                ob_created, ob_created_bull = self._detect_crosses(pc, idx, ob_created, ob_created_bull)

            # Bearish OB Creation
            if ob_created:
                ob_created = self._create_bearish_ob(df, idx, n)

            # Bullish OB Creation
            if ob_created_bull:
                ob_created_bull = self._create_bullish_ob(df, idx, n)

            # Bearish OB cleanup & alerts
            self._process_bearish_obs(df, idx, OBBearMitigation)

            # Bullish OB cleanup & alerts
            self._process_bullish_obs(df, idx, OBBullMitigation)

    def _detect_crosses(self, pc: pd.Series, idx: int, ob_created: bool, ob_created_bull: bool) -> tuple:
        """Detect crossover and crossunder events."""
        prev_pc = pc.iat[idx - 1] if not np.isnan(pc.iat[idx - 1]) else None
        cur_pc = pc.iat[idx] if not np.isnan(pc.iat[idx]) else None

        if prev_pc is not None and cur_pc is not None:
            # crossunder: previous >= -sens and current < -sens
            if prev_pc >= -self.sens and cur_pc < -self.sens:
                ob_created = True

            # crossover: previous <= sens and current > sens
            if prev_pc <= self.sens and cur_pc > self.sens:
                ob_created_bull = True

        return ob_created, ob_created_bull

    def _get_last_created_idx(self) -> int:
        """Get the index of the last created OB."""
        last_created_idx = -9999

        if len(self.short_boxes) > 0:
            last_created_idx = max([b.created_at or -9999 for b in self.short_boxes])

        if len(self.long_boxes) > 0:
            long_max = max([b.created_at or -9999 for b in self.long_boxes])
            last_created_idx = max(last_created_idx, long_max)

        return last_created_idx

    def _create_bearish_ob(self, df: pd.DataFrame, idx: int, n: int) -> bool:
        """Create bearish order block if conditions are met."""
        last_created_idx = self._get_last_created_idx()

        # Check spacing requirement
        if last_created_idx != -9999 and (idx - last_created_idx) <= 5:
            return False

        # Find first GREEN candle in range 4..15
        last_green_idx = None
        for off in range(4, 16):
            bar_idx = idx - off
            if bar_idx >= 0:
                if df['Close'].iat[bar_idx] > df['Open'].iat[bar_idx]:
                    last_green_idx = bar_idx
                    break

        if last_green_idx is not None:
            self.short_boxes.append(Box(
                left=last_green_idx,
                right=n - 1,
                top=df['High'].iat[last_green_idx],
                bottom=df['Low'].iat[last_green_idx],
                box_type=BoxType.BEARISH,
                bg_color=self.col_bearish_ob,
                border_color=self.col_bearish,
                created_at=idx
            ))

        return False  # Reset flag

    def _create_bullish_ob(self, df: pd.DataFrame, idx: int, n: int) -> bool:
        """Create bullish order block if conditions are met."""
        last_created_idx = self._get_last_created_idx()

        # Check spacing requirement
        if last_created_idx != -9999 and (idx - last_created_idx) <= 5:
            return False

        # Find first RED candle in range 4..15
        last_red_idx = None
        for off in range(4, 16):
            bar_idx = idx - off
            if bar_idx >= 0:
                if df['Close'].iat[bar_idx] < df['Open'].iat[bar_idx]:
                    last_red_idx = bar_idx
                    break

        if last_red_idx is not None:
            self.long_boxes.append(Box(
                left=last_red_idx,
                right=n - 1,
                top=df['High'].iat[last_red_idx],
                bottom=df['Low'].iat[last_red_idx],
                box_type=BoxType.BULLISH,
                bg_color=self.col_bullish_ob,
                border_color=self.col_bullish,
                created_at=idx
            ))

        return False  # Reset flag

    def _process_bearish_obs(self, df: pd.DataFrame, idx: int, OBBearMitigation: pd.Series):
        """Process bearish OBs for cleanup and alerts."""
        if len(self.short_boxes) == 0:
            return

        # Iterate backwards
        for j in range(len(self.short_boxes) - 1, -1, -1):
            sbox = self.short_boxes[j]

            # Check if mitigated
            val = OBBearMitigation.iat[idx] if idx < len(OBBearMitigation) else None
            if val is not None and not np.isnan(val) and val > sbox.top:
                self.short_boxes.pop(j)
                continue

            # Alerts
            if df['High'].iat[idx] > sbox.bottom and self.sell_alert:
                self.signals.append(Signal(
                    index=idx,
                    price=df['High'].iat[idx],
                    date=None,
                    type=SignalType.SELL,
                    symbol="\u2193",
                    color="#C21919",
                    inside_fvg=False,
                    inside_sonar=True,
                    fvg_alpha=None,
                    signalStrength=0,
                    source_strategy=['SonarlaplaceOrderBlocks']
                ))

    def _process_bullish_obs(self, df: pd.DataFrame, idx: int, OBBullMitigation: pd.Series):
        """Process bullish OBs for cleanup and alerts."""
        if len(self.long_boxes) == 0:
            return

        # Iterate backwards
        for j in range(len(self.long_boxes) - 1, -1, -1):
            lbox = self.long_boxes[j]

            # Check if mitigated
            val = OBBullMitigation.iat[idx] if idx < len(OBBullMitigation) else None
            if val is not None and not np.isnan(val) and val < lbox.bottom:
                self.long_boxes.pop(j)
                continue

            # Alerts
            if df['Low'].iat[idx] < lbox.top and self.buy_alert:
                self.signals.append(Signal(
                    index=idx,
                    price=df['Low'].iat[idx],
                    date=None,
                    type=SignalType.BUY,
                    symbol="\u2191",
                    color="#167F52",
                    inside_fvg=False,
                    inside_sonar=True,
                    fvg_alpha=None,
                    signalStrength=0,
                    source_strategy=['SonarlaplaceOrderBlocks']
                ))

    def get_signals(self) -> List[Signal]:
        """Return the list of signals generated by the strategy."""
        return self.signals

    def plot(self, df: pd.DataFrame, title: str = "Sonarlab - Order Blocks", ax=None):
        """Plot the strategy results."""
        dates = list(df.index)

        if ax is None:
            fig, ax = plt.subplots(figsize=(14, 7))

        # Draw candlesticks
        draw_candlesticks(ax, df)

        # Draw boxes
        draw_boxes(ax, self.long_boxes, dates)
        draw_boxes(ax, self.short_boxes, dates)

        # Draw signals
        draw_signals(ax, self.signals, dates, self.col_bullish, self.col_bearish)

        # Setup axes
        setup_chart_axes(ax, title)