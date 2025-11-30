import pandas as pd
from typing import List, Tuple, Any
from pandas import DataFrame

# shared helpers for UI modules

# default: do not force close open positions at end of data
_FORCE_CLOSE_AT_END = False


def set_force_close_at_end(enabled: bool) -> None:
    """Enable or disable forcing close of open positions at end of data."""
    global _FORCE_CLOSE_AT_END
    _FORCE_CLOSE_AT_END = bool(enabled)


def get_force_close_at_end() -> bool:
    """Return whether forced close at end-of-data is enabled."""
    return _FORCE_CLOSE_AT_END


def load_and_generate_signals(load_data_fn, SignalGeneratorClass, file_name) -> Tuple[DataFrame, List[Any]]:
    """Load data using load_data_fn and generate enhanced signals using SignalGeneratorClass."""
    df = load_data_fn(file_name)
    sg = SignalGeneratorClass()
    enhanced = sg.generate_from_file(df, file_name) or []
    return df, enhanced


def normalize_signals_to_df(sg, enhanced_list) -> DataFrame:
    try:
        df_display = sg.to_dataframe(enhanced_list)
    except Exception:
        rows = []
        for s in enhanced_list:
            rows.append({
                'date': getattr(s, 'date', None),
                'price': getattr(s, 'price', None),
                'type': getattr(s, 'type', None),
                'signalStrength': getattr(s, 'signalStrength', None)
            })
        df_display = pd.DataFrame(rows)
    return df_display
