import pandas as pd
import pytest
from types import SimpleNamespace

from app.agent.signal_generator import SignalGenerator
from app.model.signal import Signal


def make_df():
    dates = pd.date_range('2025-01-01', periods=5, freq='D')
    df = pd.DataFrame({
        'Open': [100, 101, 102, 103, 104],
        'High': [101, 102, 103, 104, 105],
        'Low': [99, 100, 101, 102, 103],
        'Close': [100, 101, 102, 103, 104],
    }, index=dates)
    return df


def test_generate_signals_returns_list_of_Signal():
    sg = SignalGenerator()
    df = make_df()
    signals = sg.generate_from_file(df, 'TEST')
    assert isinstance(signals, list)
    for s in signals:
        assert hasattr(s, 'signalStrength')
        assert hasattr(s, 'price')
        assert hasattr(s, 'index')


def test_to_dataframe_and_date_present():
    sg = SignalGenerator()
    df = make_df()
    signals = sg.generate_from_file(df, 'TEST')
    df_out = sg.to_dataframe(signals)
    assert 'date' in df_out.columns
    if not df_out.empty:
        assert pd.api.types.is_datetime64_any_dtype(df_out['date'])

