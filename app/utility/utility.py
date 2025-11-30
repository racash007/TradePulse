import os

import pandas as pd


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


def _normalize_column_names(cols):
    """Return a mapping from existing column names to standard names if possible."""
    mapping = {}
    lower = [c.lower() for c in cols]

    def find(names):
        for name in names:
            if name in lower:
                return cols[lower.index(name)]
        return None

    # date
    date_col = find(['date', 'timestamp'])
    if date_col:
        mapping[date_col] = 'Date'

    # close variations
    close_col = find(['close price', 'closeprice', 'close', 'close_price'])
    if close_col:
        mapping[close_col] = 'Close'

    open_col = find(['open price', 'openprice', 'open', 'open_price'])
    if open_col:
        mapping[open_col] = 'Open'

    high_col = find(['high price', 'highprice', 'high', 'high_price'])
    if high_col:
        mapping[high_col] = 'High'

    low_col = find(['low price', 'lowprice', 'low', 'low_price'])
    if low_col:
        mapping[low_col] = 'Low'

    return mapping


def _clean_numeric_series(s: pd.Series) -> pd.Series:
    """Clean numeric series by removing commas, parentheses and other nuisance characters and convert to float."""
    if s.dtype == object or pd.api.types.is_string_dtype(s):
        # remove commas and parentheses, handle negatives like (1,234.56)
        cleaned = s.astype(str).str.strip()
        # convert (123) to -123
        has_paren = cleaned.str.startswith('(') & cleaned.str.endswith(')')
        cleaned = cleaned.str.replace(',', '', regex=False)
        cleaned = cleaned.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
        # remove any non-numeric prefix/suffix (like currency symbols)
        cleaned = cleaned.str.replace(r"[^0-9.\-]", '', regex=True)
        return pd.to_numeric(cleaned, errors='coerce')
    else:
        return pd.to_numeric(s, errors='coerce')


def load_data(file_name: str, folder: str = 'data') -> pd.DataFrame:
    """
    Load OHLC data from a CSV file in resource/<folder> whose name contains the filter string.
    If file_name is an absolute/relative path to an existing file, it will be loaded directly.
    Returns a DataFrame with Date index and columns Open/High/Low/Close as numeric types.
    """
    # If a path is provided, use it directly
    if os.path.isfile(file_name):
        file_path = file_name
    else:
        # search resource folder for matching file (case-insensitive)
        root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        data_dir = os.path.join(root, 'resource', folder)
        if not os.path.isdir(data_dir):
            raise FileNotFoundError(f"Resource folder not found: {data_dir}")

        candidates = [f for f in os.listdir(data_dir) if file_name.lower() in f.lower() and f.lower().endswith('.csv')]
        if not candidates:
            raise FileNotFoundError(f"No CSV file found in {data_dir} containing '{file_name}'")
        # pick first candidate
        file_path = os.path.join(data_dir, candidates[0])

    # Read CSV
    df = pd.read_csv(file_path, dtype=str)

    # Normalize column names
    cols = list(df.columns)
    mapping = _normalize_column_names(cols)
    if mapping:
        df = df.rename(columns=mapping)

    # Ensure required columns exist
    required = ['Date', 'Open', 'High', 'Low', 'Close']
    # try to find case-insensitive matches for required columns
    for req in required:
        if req not in df.columns:
            # attempt to find a close match
            matches = [c for c in df.columns if c.lower() == req.lower()]
            if matches:
                df = df.rename(columns={matches[0]: req})

    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Required columns missing from CSV ({file_path}): {missing}")

    # Clean numeric columns
    for col in ['Open', 'High', 'Low', 'Close']:
        df[col] = _clean_numeric_series(df[col])

    # Parse Date and set index
    try:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    except Exception:
        df['Date'] = pd.to_datetime(df['Date'], infer_datetime_format=True, errors='coerce')

    if df['Date'].isna().all():
        raise ValueError(f"Date column could not be parsed in file: {file_path}")

    df = df.set_index('Date')
    # Sort by date ascending
    df = df.sort_index()

    return df