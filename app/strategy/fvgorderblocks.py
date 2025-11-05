# -------------------------
# 1) FVG Order Blocks [BigBeluga] (full logic)
# -------------------------
import math
from typing import List, Dict, Any

import matplotlib.pyplot as plt
import pandas as pd
from pandas import DataFrame

# resilient imports: prefer package-style imports, fall back to local module imports
try:
    from app.strategy.signal import Signal
    from app.strategy.strategy import Strategy
    from app.utility.utility import atr_series, hex_to_rgba, clamp
except Exception:
    from strategy.signal import Signal
    from strategy.strategy import Strategy
    from utility.utility import atr_series, hex_to_rgba, clamp


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

        # storage for created "boxes" (dicts)
        self.bull_boxes: List[Dict[str, Any]] = []
        self.bear_boxes: List[Dict[str, Any]] = []
        # temporary boxes for visualizing gaps
        self.temp_boxes: List[Dict[str, Any]] = []
        # signals: list of dicts {index, price, symbol, color}
        self.signals: List[Signal] = []

    def run(self, df: pd.DataFrame):
        """
        df: DataFrame with columns ['Open','High','Low','Close'] indexed by date
        After run, self.bull_boxes, self.bear_boxes and self.signals will be populated.
        """
        n = len(df)
        if n == 0:
            return

        # ATR replicating ta.atr(200)
        atr = atr_series(df, period=200)

        # Filters
        # note: pine uses low-high[2] etc, so we exactly mirror those formulas:
        filt_up = (df['Low'] - df['High'].shift(2)) / df['Low'] * 100
        filt_dn = (df['Low'].shift(2) - df['High']) / df['Low'].shift(2) * 100

        max_up = filt_up.rolling(self.window_size, min_periods=1).max()
        max_dn = filt_dn.rolling(self.window_size, min_periods=1).max()


        # Iterate bars in chronological order (0..n-1) like pine
        for idx in range(n):
            # check lookback gating: (last_bar_index - bar_index) < loockback
            if (n - 1 - idx) < self.lookback:
                # compute isBull/isBear for this bar exactly as pine
                # guard shifts: ensure idx >= 2 for [2] references
                if idx >= 2:
                    isBull_gap = (df['High'].shift(2).iat[idx] < df['Low'].iat[idx]
                                  and df['High'].shift(2).iat[idx] < df['High'].shift(1).iat[idx]
                                  and df['Low'].shift(2).iat[idx] < df['Low'].iat[idx]
                                  and (filt_up.iat[idx] > self.filter_gap))
                    isBear_gap = (df['Low'].shift(2).iat[idx] > df['High'].iat[idx]
                                  and df['Low'].shift(2).iat[idx] > df['Low'].shift(1).iat[idx]
                                  and df['High'].shift(2).iat[idx] > df['High'].iat[idx]
                                  and (filt_dn.iat[idx] > self.filter_gap))
                else:
                    isBull_gap = False
                    isBear_gap = False
            else:
                isBull_gap = False
                isBear_gap = False

            # --- Logic for Bullish Imbalance (Pine exact reproduction) ---
            if isBull_gap:
                self.check_temp_bullish_boxes(df, filt_up, idx, n)

                # Permanent box (pine: left=bar_index-1, top=high[2], right=last_bar_index, bottom=high[2]-atr)
                self.check_bullish_boxes(atr, df, filt_up, idx, max_up, n)

            # --- Logic for Bearish Imbalance (Pine exact reproduction) ---
            if isBear_gap:
                self.check_temp_bearish_boxes(df, filt_dn, idx, n)

                self.check_bearish_boxes(atr, df, filt_dn, idx, max_dn, n)


            # --- Logic to handle broken levels & signals & nested boxes & size limits ---
            # We do these checks at each bar like pine (for current bar 'idx').

            self.remove_broken_and_signal_bull_boxes(df, idx, isBull_gap)

            # Nested-bull removal (pine: remove box if another top1 < top and top1 > bottom)
            self.remove_nested_bull_boxes()

            # Bear boxes broken detection & signals
            self.remove_broken_and_signal_bear_boxes(df, idx, isBear_gap)

            # Nested-bear removal (same logic pattern)
            self.remove_nested_bear_boxes()

            # Limit the number of displayed boxes to the specified amount (pine logic)
            self.remove_additional_boxes()

        # final "barstate.islast" mimic: extend boxes slightly to the right (pine set_right to bar_index+15)
        # we will extend to n-1 + 15 to mimic
        right_ext = n - 1 + 15
        for b in self.bull_boxes:
            b['right'] = right_ext
        for b in self.bear_boxes:
            b['right'] = right_ext
        for t in self.temp_boxes:
            t['right'] = min(t['right'], n - 1)  # temp limited

    def remove_additional_boxes(self):
        while len(self.bull_boxes) >= self.box_amount:
            # pine: if boxes1.size() >= box_amount box.delete(boxes1.shift())
            # shift() removes first element; so pop(0)
            self.bull_boxes.pop(0)
        while len(self.bear_boxes) >= self.box_amount:
            self.bear_boxes.pop(0)

    def remove_nested_bear_boxes(self):
        remove_bear_indices = set()
        for i_outer, box in enumerate(self.bear_boxes):
            for i_inner, box1 in enumerate(self.bear_boxes):
                if i_outer == i_inner:
                    continue
                top1 = box1['top']
                top_ = box['top']
                bottom1 = box1['bottom']
                bottom_ = box['bottom']
                if (top1 < top_) and (top1 > bottom_):
                    remove_bear_indices.add(i_outer)
                    break
        if remove_bear_indices:
            self.bear_boxes = [b for i, b in enumerate(self.bear_boxes) if i not in remove_bear_indices]

    def remove_broken_and_signal_bear_boxes(self, df: DataFrame, idx: int, isBear_gap: bool):
        to_delete_bear_indices = set()
        for bi, box in enumerate(self.bear_boxes):
            # broken if low > box.top (pine: if low > box.get_top(box_id))
            if df['Low'].iat[idx] > box['top']:
                box['border_width'] = 0
                box['bg_color'] = "#E6E6E6"
                box['broken'] = True
                if not self.show_broken:
                    to_delete_bear_indices.add(bi)

            # signal condition (pine):
            # if high < box.get_bottom(box_id) and high[1] >= box.get_bottom(box_id) and not isBear_gap and show_signal
            if self.show_signal and (idx >= 1):
                if (df['High'].iat[idx] < box['bottom'] <= df['High'].shift(1).iat[idx] and (
                        not isBear_gap)):
                    label_idx = idx - 1
                    price_for_label = df['High'].shift(1).iat[idx]
                    self.signals.append(
                        Signal(index=label_idx, price=price_for_label, type_="bearish", symbol="\ufe40", color=self.col_bear)
                    )

        if to_delete_bear_indices:
            self.bear_boxes = [b for i, b in enumerate(self.bear_boxes) if i not in to_delete_bear_indices]

    def remove_nested_bull_boxes(self):
        remove_bull_indices = set()
        for i_outer, box in enumerate(self.bull_boxes):
            for i_inner, box1 in enumerate(self.bull_boxes):
                if i_outer == i_inner:
                    continue
                top1 = box1['top']
                top_ = box['top']
                bottom1 = box1['bottom']
                bottom_ = box['bottom']
                if (top1 < top_) and (top1 > bottom_):
                    # pine: box.delete(box_id) and boxes1.remove(box_id)
                    remove_bull_indices.add(i_outer)
                    break
        if remove_bull_indices:
            self.bull_boxes = [b for i, b in enumerate(self.bull_boxes) if i not in remove_bull_indices]

    def remove_broken_and_signal_bull_boxes(self, df: DataFrame, idx: int, isBull_gap: bool):
        # Bull boxes broken detection & signals
        to_delete_bull_indices = set()
        for bi, box in enumerate(self.bull_boxes):
            # broken if high < box.bottom (pine: if high < box.get_bottom(box_id))
            if df['High'].iat[idx] < box['bottom']:
                # set border_width 0 and background to chart fg (simulated as nearly opaque grey)
                box['border_width'] = 0
                box['bg_color'] = "#E6E6E6"  # chart.fg_color approximation (light grey)
                box['broken'] = True
                if not self.show_broken:
                    to_delete_bull_indices.add(bi)

            # signal condition (pine):
            # if low > box.get_top(box_id) and low[1] <= box.get_top(box_id) and not isBull_gap and show_signal
            if self.show_signal and (idx >= 1):
                if (df['Low'].iat[idx] > box['top'] >= df['Low'].shift(1).iat[idx] and (
                        not isBull_gap)):
                    label_idx = idx - 1
                    price_for_label = df['Low'].shift(1).iat[idx]
                    self.signals.append(
                        Signal(index=label_idx, price=price_for_label, type_="bullish", symbol="\ufe3d", color=self.col_bull)
                    )

        # remove bull boxes flagged
        if to_delete_bull_indices:
            self.bull_boxes = [b for i, b in enumerate(self.bull_boxes) if i not in to_delete_bull_indices]

    def check_bearish_boxes(self, atr: pd.Series, df: DataFrame, filt_dn: pd.Series, idx: int, max_dn: pd.Series,
                            n: int):
        if idx >= 2 and not math.isnan(atr.iat[idx]):
            top_val = df['Low'].shift(2).iat[idx] + atr.iat[idx]
            bottom_val = df['Low'].shift(2).iat[idx]
            percent_val = filt_dn.iat[idx]
            p_norm = percent_val / (
                max_dn.iat[idx] if (not math.isnan(max_dn.iat[idx]) and max_dn.iat[idx] != 0) else 1.0)
            alpha = clamp(0.15 + 0.5 * (p_norm if p_norm > 0 else 0), 0.06, 0.7)
            box = {
                "left": idx - 1,
                "right": n - 1,
                "top": top_val,
                "bottom": bottom_val,
                "type": "bear",
                "percent": percent_val,
                "alpha": alpha,
                "border_color": self.col_bear,
                "bg_color": self.col_bear,
                "broken": False,
                "border_width": 1
            }
            self.bear_boxes.append(box)

    def check_temp_bearish_boxes(self, df: DataFrame, filt_dn: pd.Series, idx: int, n: int):
        if self.show_imb:
            left = idx - 1
            right = idx + 5
            top_v = df['High'].iat[idx]
            bottom_v = df['Low'].shift(2).iat[idx]
            top_normal = max(top_v, bottom_v)
            bottom_normal = min(top_v, bottom_v)
            temp = {
                "left": left,
                "right": min(right, n - 1),
                "top": top_normal,
                "bottom": bottom_normal,
                "type": "temp_bear",
                "percent": filt_dn.iat[idx],
                "alpha": 0.12
            }
            self.temp_boxes.append(temp)

    def check_bullish_boxes(self, atr: pd.Series, df: DataFrame, filt_up: pd.Series, idx: int, max_up: pd.Series,
                            n: int):
        if idx >= 2 and not math.isnan(atr.iat[idx]):
            top_val = df['High'].shift(2).iat[idx]
            bottom_val = top_val - atr.iat[idx]
            percent_val = filt_up.iat[idx]
            p_norm = percent_val / (
                max_up.iat[idx] if (not math.isnan(max_up.iat[idx]) and max_up.iat[idx] != 0) else 1.0)
            # gradient-like alpha: map p_norm to alpha
            alpha = clamp(0.15 + 0.5 * (p_norm if p_norm > 0 else 0), 0.06, 0.7)
            box = {
                "left": idx - 1,
                "right": n - 1,  # will be extended like set_right
                "top": top_val,
                "bottom": bottom_val,
                "type": "bull",
                "percent": percent_val,
                "alpha": alpha,
                "border_color": self.col_bull,
                "bg_color": self.col_bull,
                "broken": False,
                "border_width": 1
            }
            self.bull_boxes.append(box)

    def check_temp_bullish_boxes(self, df: DataFrame, filt_up: pd.Series, idx: int, n: int):
        if self.show_imb:
            # Temporary box representing the raw gap (pine used left=bar_index-1, top=low, right=bar_index+5, bottom=high[2])
            left = idx - 1
            right = idx + 5
            top_v = df['Low'].iat[idx]
            bottom_v = df['High'].shift(2).iat[idx]
            # normalize top/bottom (pine uses these values possibly reversed; ensure top>bottom for plotting)
            top_normal = max(top_v, bottom_v)
            bottom_normal = min(top_v, bottom_v)
            temp = {
                "left": left,
                "right": min(right, n - 1),
                "top": top_normal,
                "bottom": bottom_normal,
                "type": "temp_bull",
                "percent": filt_up.iat[idx],
                "alpha": 0.12
            }
            self.temp_boxes.append(temp)

    def plot(self, df: pd.DataFrame, title: str = "FVG Order Blocks [BigBeluga]", ax=None):
        """
        Draw candles and boxes using matplotlib. Uses self.bull_boxes/self.bear_boxes/self.temp_boxes/self.signals created by run().
        """
        import matplotlib.dates as mdates
        from matplotlib.patches import Rectangle
        dates = list(df.index)
        # prepare figure
        if ax is None:
            fig, ax = plt.subplots(figsize=(14, 7))
        ax.set_title(title, fontsize=16, fontweight='bold')

        # draw candlesticks manually
        width = 0.6  # days
        candle_width = 0.6
        for i, dt in enumerate(dates):
            o = df['Open'].iat[i]
            h = df['High'].iat[i]
            l = df['Low'].iat[i]
            c = df['Close'].iat[i]
            color = '#167F52' if c >= o else '#C21919'  # green / red using bull/bear
            # wick
            ax.plot([mdates.date2num(dt), mdates.date2num(dt)], [l, h], color=color, linewidth=0.7)
            # body
            rect = Rectangle((mdates.date2num(dt) - candle_width / 2, min(o, c)), candle_width, max(abs(c - o), 0.0001),
                             facecolor=color, edgecolor=color, linewidth=0.5, zorder=2)
            ax.add_patch(rect)

        # draw permanent bull boxes (green-ish)
        for b in self.bull_boxes:
            left = mdates.date2num(dates[b['left']]) if b['left'] >= 0 and b['left'] < len(dates) else mdates.date2num(
                dates[0])
            # compute right x coordinate, if right index beyond last date, extend by fraction of day
            right_idx = min(b['right'], len(dates) - 1)
            right = mdates.date2num(dates[right_idx]) + 0.0  # no extra extended days for neatness
            top = b['top']
            bottom = b['bottom']
            face_rgba = hex_to_rgba(b['bg_color'], b['alpha'])
            edge_rgba = hex_to_rgba(b['border_color'], 1.0 if b['border_width'] > 0 else 0.0)
            rect = Rectangle((left, bottom), right - left, top - bottom, facecolor=face_rgba, edgecolor=edge_rgba,
                             linewidth=b['border_width'], zorder=1)
            ax.add_patch(rect)
            # add percent text on box right (similar to text_halign=right)
            try:
                pct_text = f"{b['percent']:.2f}%"
            except:
                pct_text = ""
            ax.text(right - (right - left) * 0.02, (top + bottom) / 2, pct_text, verticalalignment='center',
                    horizontalalignment='right', fontsize=8, color='black', zorder=3)

        # draw permanent bear boxes (red-ish)
        for b in self.bear_boxes:
            left = mdates.date2num(dates[b['left']]) if b['left'] >= 0 and b['left'] < len(dates) else mdates.date2num(
                dates[0])
            right_idx = min(b['right'], len(dates) - 1)
            right = mdates.date2num(dates[right_idx])
            top = b['top']
            bottom = b['bottom']
            face_rgba = hex_to_rgba(b['bg_color'], b['alpha'])
            edge_rgba = hex_to_rgba(b['border_color'], 1.0 if b['border_width'] > 0 else 0.0)
            rect = Rectangle((left, bottom), right - left, top - bottom, facecolor=face_rgba, edgecolor=edge_rgba,
                             linewidth=b['border_width'], zorder=1)
            ax.add_patch(rect)
            try:
                pct_text = f"{b['percent']:.2f}%"
            except:
                pct_text = ""
            ax.text(right - (right - left) * 0.02, (top + bottom) / 2, pct_text, verticalalignment='center',
                    horizontalalignment='right', fontsize=8, color='black', zorder=3)

        # draw temp boxes (light)
        for t in self.temp_boxes:
            if t['left'] < 0 or t['right'] < 0:
                continue
            left = mdates.date2num(dates[max(0, t['left'])])
            right = mdates.date2num(dates[min(len(dates) - 1, t['right'])])
            top = t['top']
            bottom = t['bottom']
            rect = Rectangle((left, bottom), right - left, top - bottom, facecolor=(0.7, 0.7, 0.95, t['alpha']),
                             edgecolor='none', zorder=0)
            ax.add_patch(rect)
            # draw percent text (if provided)
            try:
                pct_text = f"{t['percent']:.2f}%"
            except:
                pct_text = ""
            ax.text(left + (right - left) * 0.02, (top + bottom) / 2, pct_text, verticalalignment='center',
                    horizontalalignment='left', fontsize=8, color='black', zorder=2)

        # draw signals labels (︽ or ﹀)
        for s in self.signals:
            # support both Signal objects and dict-like signals
            if hasattr(s, 'index'):
                idx = s.index
                price = s.price
                symbol = s.symbol
                color = s.color
            elif isinstance(s, dict):
                idx = s.get('index')
                price = s.get('price')
                symbol = s.get('symbol')
                color = s.get('color')
            else:
                continue
            if idx is None or price is None:
                continue
            if idx < 0 or idx >= len(dates):
                continue
            x = mdates.date2num(dates[int(idx)])
            y = price
            sym = symbol if symbol is not None else ("\u2191" if (hasattr(s, 'type') and str(s.type).lower().startswith('bull')) else "\u2193")
            col = color if color is not None else ('#167F52' if (hasattr(s, 'type') and str(s.type).lower().startswith('bull')) else '#C21919')
            ax.text(x, y, sym, fontsize=12, fontweight='bold', ha='center', va='center', color=col, zorder=4)

        ax.set_ylabel("Price", fontsize=12, fontweight='bold')
        ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.4)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        plt.xticks(rotation=45)
        plt.tight_layout()
        # If ax was created here, show the plot
        # Removed ax.figure.show() for Tkinter embedding compatibility
        # if ax is not None and hasattr(ax, 'figure') and hasattr(ax.figure, 'show'):
        #     ax.figure.show()

    def get_signals(self):
        return self.signals
