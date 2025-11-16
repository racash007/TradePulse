"""
Common plotting utilities for strategies.
"""
from typing import List
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import pandas as pd

from app.model.box import Box
from app.model.signal import Signal
from app.utility.utility import hex_to_rgba


def draw_candlesticks(ax, df: pd.DataFrame, bull_color: str = '#167F52', bear_color: str = '#C21919'):
    """Draw candlestick chart on the given axis."""
    dates = list(df.index)
    candle_width = 0.6

    for i, dt in enumerate(dates):
        o = df['Open'].iat[i]
        h = df['High'].iat[i]
        l = df['Low'].iat[i]
        c = df['Close'].iat[i]
        color = bull_color if c >= o else bear_color

        # wick
        ax.plot([mdates.date2num(dt), mdates.date2num(dt)], [l, h], color=color, linewidth=0.7)
        # body
        rect = Rectangle(
            (mdates.date2num(dt) - candle_width / 2, min(o, c)),
            candle_width,
            max(abs(c - o), 0.0001),
            facecolor=color,
            edgecolor=color,
            linewidth=0.5,
            zorder=2
        )
        ax.add_patch(rect)


def draw_box(ax, box: Box, dates: List, default_alpha: float = 0.25):
    """Draw a single box on the given axis."""
    if box.left < 0 or box.left >= len(dates):
        left = mdates.date2num(dates[0])
    else:
        left = mdates.date2num(dates[box.left])

    right_idx = min(box.right, len(dates) - 1)
    right = mdates.date2num(dates[right_idx])

    alpha = box.alpha if box.alpha else default_alpha
    face_rgba = hex_to_rgba(box.bg_color, alpha)
    edge_rgba = hex_to_rgba(box.border_color, 1.0 if box.border_width > 0 else 0.0)

    rect = Rectangle(
        (left, box.bottom),
        right - left,
        box.top - box.bottom,
        facecolor=face_rgba,
        edgecolor=edge_rgba,
        linewidth=box.border_width,
        zorder=1
    )
    ax.add_patch(rect)

    # Add percent text if available
    if box.percent is not None:
        try:
            pct_text = f"{box.percent:.2f}%"
            ax.text(
                right - (right - left) * 0.02,
                (box.top + box.bottom) / 2,
                pct_text,
                verticalalignment='center',
                horizontalalignment='right',
                fontsize=8,
                color='black',
                zorder=3
            )
        except:
            pass


def draw_boxes(ax, boxes: List[Box], dates: List, default_alpha: float = 0.25):
    """Draw multiple boxes on the given axis."""
    for box in boxes:
        draw_box(ax, box, dates, default_alpha)


def draw_signals(ax, signals: List[Signal], dates: List, bull_color: str = '#167F52', bear_color: str = '#C21919'):
    """Draw signal markers on the given axis."""
    for s in signals:
        if s.index < 0 or s.index >= len(dates):
            continue

        x = mdates.date2num(dates[int(s.index)])
        y = s.price

        # Determine symbol and color
        is_bull = s.type.value == 'buy' if hasattr(s.type, 'value') else 'bull' in str(s.type).lower()
        sym = s.symbol if s.symbol else ('↑' if is_bull else '↓')
        col = s.color if s.color else (bull_color if is_bull else bear_color)

        ax.text(x, y, sym, fontsize=12, fontweight='bold', ha='center', va='center', color=col, zorder=4)


def setup_chart_axes(ax, title: str, ylabel: str = "Price"):
    """Configure common chart settings."""
    ax.set_title(title, fontsize=16, fontweight='bold')
    ax.set_ylabel(ylabel, fontsize=12, fontweight='bold')
    ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.4)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    plt.xticks(rotation=45)
    plt.tight_layout()