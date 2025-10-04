# -------------------------
# 2) Sonarlab - Order Blocks (full logic)
# -------------------------
import math
from typing import List, Dict, Any
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle

from app.strategy.strategy import Strategy
from app.utility.utility import atr_series, hex_to_rgba, clamp


class SonarlabOrderBlocks(Strategy):
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
     - For creation, ensure gap from previously created OBs: cross_index - cross_index[1] > 5 (replicated by ensuring i - last_ob_idx > 5)
     - loops offsets 4..15 to find first RED/GREEN candle to place OB
     - cleanup and alert rules replicated exactly
    """

    def __init__(self,
                 sensitivity: int = 28,
                 OBMitigationType: str = "Close",
                 col_bullish: str = "#5db49e",
                 col_bullish_ob: str = "#64C4AC",  # will apply alpha
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

        # storage
        self.long_boxes: List[Dict[str, Any]] = []
        self.short_boxes: List[Dict[str, Any]] = []
        self.signals: List[Dict[str, Any]] = []

    def run(self, df: pd.DataFrame):
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
            OBBullMitigation = df['Low']  # using low (Wick)
            OBBearMitigation = df['High']  # using high (Wick)

        # emulate pine boolean/state variables
        ob_created = False
        ob_created_bull = False
        last_cross_index = None  # like cross_index var in pine (we store last used cross creation index)

        # iterate bars
        for idx in range(n):
            # detect crossunder (pc crosses under -sens)
            if idx >= 1:
                prev_pc = pc.iat[idx - 1] if not np.isnan(pc.iat[idx - 1]) else None
                cur_pc = pc.iat[idx] if not np.isnan(pc.iat[idx]) else None
                # crossunder: previous >= -sens and current < -sens
                if (prev_pc is not None and cur_pc is not None and prev_pc >= -self.sens and cur_pc < -self.sens):
                    ob_created = True
                    last_cross_index = idx  # cross_index := bar_index
                # crossover: previous <= sens and current > sens
                if (prev_pc is not None and cur_pc is not None and prev_pc <= self.sens and cur_pc > self.sens):
                    ob_created_bull = True
                    last_cross_index = idx

            # -------------------------------
            # Bearish OB Creation (pine logic)
            # -------------------------------
            if ob_created:
                # pine: if ob_created and cross_index - cross_index[1] > 5 We simulate by ensuring at least 6 bars
                # since the last created cross (if we have prior creation) But pine's cross_index[1] is previous
                # value; here we simply use last_ob_creation_idx to guard multiple within 5 bars. We'll track
                # 'last_created_ob_idx' to enforce spacing. Simpler: require idx - last_created_ob_idx > 5 if exists.
                pass

            # We'll maintain a small variable to hold the last created OB global index to enforce spacing
            # (initialize on first creation)
            # We'll create OB when ob_created True and (no OB created recently within 5 bars)
            if ob_created:
                # find if there was a previously created OB (either bull or bear) to match pine condition cross_index
                # - cross_index[1] > 5, we require idx - prev_cross_index > 5 We don't have cross_index[1]; we will
                # use a local guard: don't create if any creation occurred within last 5 bars.
                recently_created = False
                # look for last created OB index in our short/long boxes: use last created's 'created_at' if present
                last_created_idx = None
                if len(self.short_boxes) > 0:
                    last_created_idx = max([b.get('created_at', -9999) for b in self.short_boxes])
                if len(self.long_boxes) > 0:
                    last_created_idx = max(last_created_idx if last_created_idx is not None else -9999,
                                           max([b.get('created_at', -9999) for b in self.long_boxes]))
                if last_created_idx is not None and (idx - last_created_idx) <= 5:
                    recently_created = True

                if not recently_created:
                    # loop through offsets 4..15 and find first GREEN candle (close[i] > open[i]) as in pine
                    last_green_idx = None
                    for off in range(4, 16):
                        bar_idx = idx - off
                        if bar_idx >= 0:
                            if df['Close'].iat[bar_idx] > df['Open'].iat[bar_idx]:
                                last_green_idx = bar_idx
                                break
                    if last_green_idx is not None:
                        drawShortBox = {
                            "left": last_green_idx,
                            "right": n - 1,
                            "top": df['High'].iat[last_green_idx],
                            "bottom": df['Low'].iat[last_green_idx],
                            "bg_color": self.col_bearish_ob,
                            "border_color": self.col_bearish,
                            "created_at": idx,
                            "type": "bearish"
                        }
                        self.short_boxes.append(drawShortBox)
                # reset ob_created flag in pine it's not reset explicitly; but next bars ob_created may be reset by
                # cross detection
                ob_created = False

            # -------------------------------
            # Bullish OB Creation
            # -------------------------------
            if ob_created_bull:
                last_created_idx = None
                if len(self.short_boxes) > 0:
                    last_created_idx = max([b.get('created_at', -9999) for b in self.short_boxes])
                if len(self.long_boxes) > 0:
                    last_created_idx = max(last_created_idx if last_created_idx is not None else -9999,
                                           max([b.get('created_at', -9999) for b in self.long_boxes]))
                recently_created = False
                if last_created_idx is not None and (idx - last_created_idx) <= 5:
                    recently_created = True

                if not recently_created:
                    last_red_idx = None
                    for off in range(4, 16):
                        bar_idx = idx - off
                        if bar_idx >= 0:
                            if df['Close'].iat[bar_idx] < df['Open'].iat[bar_idx]:
                                last_red_idx = bar_idx
                                break
                    if last_red_idx is not None:
                        drawLongBox = {
                            "left": last_red_idx,
                            "right": n - 1,
                            "top": df['High'].iat[last_red_idx],
                            "bottom": df['Low'].iat[last_red_idx],
                            "bg_color": self.col_bullish_ob,
                            "border_color": self.col_bullish,
                            "created_at": idx,
                            "type": "bullish"
                        }
                        self.long_boxes.append(drawLongBox)
                ob_created_bull = False

            # -----------------
            # Bearish OB cleanup & alerts (pine)
            # -----------------
            # if array.size(shortBoxes) > 0
            if len(self.short_boxes) > 0:
                # iterate backwards as pine does
                for j in range(len(self.short_boxes) - 1, -1, -1):
                    sbox = self.short_boxes[j]
                    top = sbox['top']
                    bot = sbox['bottom']
                    # If the OBBearMitigation > top -> remove the OB
                    # (pine: if OBBearMitigation > top array.remove & box.delete)
                    # OBBearMitigation is a series: check current idx value
                    val = OBBearMitigation.iat[idx] if idx < len(OBBearMitigation) else None
                    if (val is not None) and (not np.isnan(val)) and (val > top):
                        # remove
                        self.short_boxes.pop(j)
                        continue
                    # Alerts
                    if (df['High'].iat[idx] > bot) and self.sell_alert:
                        # replicate alert('Price inside Bearish OB') once per bar: we simply append signal
                        self.signals.append(
                            {"index": idx, "price": df['High'].iat[idx], "signal": "sell", "type": "bearish"})

            # -----------------
            # Bullish OB cleanup & alerts (pine)
            # -----------------
            if len(self.long_boxes) > 0:
                for j in range(len(self.long_boxes) - 1, -1, -1):
                    lbox = self.long_boxes[j]
                    bot = lbox['bottom']
                    top = lbox['top']
                    val = OBBullMitigation.iat[idx] if idx < len(OBBullMitigation) else None
                    if (val is not None) and (not np.isnan(val)) and (val < bot):
                        self.long_boxes.pop(j)
                        continue
                    if (df['Low'].iat[idx] < top) and self.buy_alert:
                        self.signals.append(
                            {"index": idx, "price": df['Low'].iat[idx], "signal": "buy", "type": "bullish"})

    def plot(self, df: pd.DataFrame, title: str = "Sonarlab - Order Blocks"):
        dates = list(df.index)
        fig, ax = plt.subplots(figsize=(14, 7))
        ax.set_title(title, fontsize=16, fontweight='bold')
        # draw candles
        width = 0.6
        for i, dt in enumerate(dates):
            o = df['Open'].iat[i]
            h = df['High'].iat[i]
            l = df['Low'].iat[i]
            c = df['Close'].iat[i]
            color = '#167F52' if c >= o else '#C21919'
            ax.plot([mdates.date2num(dt), mdates.date2num(dt)], [l, h], color=color, linewidth=0.7)
            rect = Rectangle((mdates.date2num(dt) - width / 2, min(o, c)), width, max(abs(c - o), 0.0001),
                             facecolor=color, edgecolor=color, linewidth=0.5, zorder=2)
            ax.add_patch(rect)

        # draw long_boxes (bullish)
        for b in self.long_boxes:
            left = mdates.date2num(dates[b['left']])
            right = mdates.date2num(dates[min(b['right'], len(dates) - 1)])
            top = b['top']
            bottom = b['bottom']
            face_rgba = hex_to_rgba(b['bg_color'], 0.25)
            edge_rgba = hex_to_rgba(b['border_color'], 1.0)
            rect = Rectangle((left, bottom), right - left, top - bottom, facecolor=face_rgba, edgecolor=edge_rgba,
                             linewidth=1, zorder=1)
            ax.add_patch(rect)

        # draw short_boxes (bearish)
        for b in self.short_boxes:
            left = mdates.date2num(dates[b['left']])
            right = mdates.date2num(dates[min(b['right'], len(dates) - 1)])
            top = b['top']
            bottom = b['bottom']
            face_rgba = hex_to_rgba(b['bg_color'], 0.25)
            edge_rgba = hex_to_rgba(b['border_color'], 1.0)
            rect = Rectangle((left, bottom), right - left, top - bottom, facecolor=face_rgba, edgecolor=edge_rgba,
                             linewidth=1, zorder=1)
            ax.add_patch(rect)

        # draw alerts signals
        for s in self.signals:
            idx = s['index']
            if idx < 0 or idx >= len(dates):
                continue
            x = mdates.date2num(dates[idx])
            y = s['price']
            sym = '↑' if s['signal'] == 'buy' else '↓'
            color = '#167F52' if s['signal'] == 'buy' else '#C21919'
            ax.text(x, y, sym, fontsize=12, color=color, fontweight='bold', ha='center', va='center', zorder=4)

        ax.set_ylabel("Price", fontsize=12, fontweight='bold')
        ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.4)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.show()



