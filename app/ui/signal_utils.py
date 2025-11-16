"""
Common signal filtering and processing utilities for UI components.
"""
from typing import List
import pandas as pd

from app.model.SignalType import SignalType
from app.model.signal import Signal


def filter_buy_signals(signals: List[Signal]) -> List[Signal]:
    """Filter signals to only include BUY signals with non-zero strength."""
    return [
        s for s in signals
        if s.signalStrength and s.signalStrength > 0 and s.type == SignalType.BUY
    ]


def format_date_column(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Format a date column to YYYY-MM-DD string format."""
    if column in df.columns:
        try:
            df[column] = pd.to_datetime(df[column], errors='coerce').dt.strftime('%Y-%m-%d')
        except Exception:
            pass
    return df


def format_trades_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Format entry_date and exit_date columns in trades DataFrame."""
    df = df.copy()
    for col in ['entry_date', 'exit_date']:
        df = format_date_column(df, col)
    return df


def format_numeric_columns(df: pd.DataFrame, columns: dict) -> pd.DataFrame:
    """Format numeric columns with specified format strings.

    Args:
        df: DataFrame to format
        columns: Dict mapping column names to format strings (e.g., {'pnl': '{:.2f}'})
    """
    df = df.copy()
    for col, fmt in columns.items():
        if col in df.columns:
            df[col] = df[col].apply(lambda x: fmt.format(x) if pd.notna(x) else '')
    return df
