import os
import pandas as pd
from app.utility.utility import load_data


def get_security_name(file_name: str) -> str:
    """Extract security name from file name.

    Expected pattern: DD-MM-YYYY-TO-DD-MM-YYYY-SECURITY-...
    """
    try:
        parts = file_name.split("-")
        if len(parts) >= 8:
            return parts[7]
        else:
            # Fallback: return filename without extension
            return file_name.rsplit('.', 1)[0] if '.' in file_name else file_name
    except (IndexError, AttributeError):
        return file_name


def read_csv_into_df(csv_input: str) -> pd.DataFrame:
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
    df = normalize_ohlc_columns(df)

    # parse Date
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.set_index('Date')

    return df


def normalize_ohlc_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize column names to standard OHLC format.
    Converts various column naming conventions to Open/High/Low/Close.
    """
    cols = list(df.columns)
    mapping = {}
    lower = [c.lower() for c in cols]

    # Map common variations
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

    return df
