import numpy as np
import pandas as pd
import os


def atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder-style ATR approximation: rolling mean of true range for period."""
    high = df['High']
    low = df['Low']
    close = df['Close']
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()


def hex_to_rgba(hex_color: str, alpha: float = 1.0):
    """Convert '#RRGGBB' to RGBA tuple with alpha in [0,1]."""
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return r, g, b, alpha


def clamp(v, a, b):
    return max(a, min(b, v))

# -------------------------
# Dummy dataset and run examples
# -------------------------
def load_data(filter: str):
    """
    Load OHLC data from a CSV file in resource/data whose name contains the filter string.
    If no file matches, raises FileNotFoundError.
    """
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'resource', 'data')
    files = [f for f in os.listdir(data_dir) if filter in f and f.endswith('.csv')]
    if not files:
        raise FileNotFoundError(f"No CSV file found in {data_dir} containing '{filter}'")
    file_path = os.path.join(data_dir, files[0])
    df = pd.read_csv(file_path)
    # Select and rename required columns
    df = df[['Date', 'Close Price', 'Open Price', 'High Price', 'Low Price']].rename(
        columns={
            'Close Price': 'Close',
            'Open Price': 'Open',
            'High Price': 'High',
            'Low Price': 'Low'
        }
    )
    # Ensure numeric types for OHLC columns, handling commas in numbers
    for col in ['Open', 'High', 'Low', 'Close']:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce')
    # Try to parse date column if present
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
    return df