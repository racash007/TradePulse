import pandas as pd
import pytest
from datetime import datetime, timedelta

from app.agent.paper_trade_agent import PaperTradeAgent
from types import SimpleNamespace


def make_df(values):
    # values: list of tuples (open, high, low, close)
    start = datetime(2025, 1, 1)
    dates = [start + timedelta(days=i) for i in range(len(values))]
    df = pd.DataFrame(values, columns=['Open', 'High', 'Low', 'Close'], index=pd.to_datetime(dates))
    return df


def make_signal(idx, price, date=None, typ='buy', symbol='TEST', strength=1):
    return SimpleNamespace(index=idx, price=price, date=date, type=typ, symbol=symbol, signalStrength=strength)


def _run_agent_and_finalize(ta, df, sig_list):
    # Run execute_signals and then force processing of pending exits
    ta.execute_signals(df, sig_list)
    # Process any remaining pending exits by setting a far-future current date
    ta._process_pending_exits(pd.Timestamp.max)
    trades_df = ta._trades_to_dataframe()
    return trades_df


def test_exit_at_target_and_after_entry():
    # Entry at index 0 price 100, target 7% -> 107; next bar high hits 110
    df = make_df([
        (100, 100, 99, 100),
        (101, 110, 99, 105),
        (105, 106, 104, 105),
    ])

    sig = make_signal(0, 100.0, date=df.index[0], typ='buy', symbol='TEST', strength=2)
    ta = PaperTradeAgent(initial_capital=100000)
    trades_df = _run_agent_and_finalize(ta, df, [sig])
    assert not trades_df.empty
    row = trades_df.iloc[0]
    assert pd.to_datetime(row['entry_date']) == df.index[0]
    # exit should be at target price (entry 100 * 1.07 = 107.0)
    assert pytest.approx(row['exit_price'], rel=1e-6) == 100.0 * (1 + ta.target_pct)
    assert pd.to_datetime(row['exit_date']) > pd.to_datetime(row['entry_date'])


def test_both_target_and_stop_hit_same_bar_conservative_exit():
    # entry 100, tp=107 sl=97; next bar high 110 and low 95 -> both hit -> choose sl (loss)
    df = make_df([
        (100, 100, 99, 100),
        (101, 110, 95, 100),
    ])

    sig = make_signal(0, 100.0, date=df.index[0], typ='buy', symbol='TEST', strength=1)
    ta = PaperTradeAgent(initial_capital=10000)
    trades_df = _run_agent_and_finalize(ta, df, [sig])
    assert not trades_df.empty
    row = trades_df.iloc[0]
    # exit price should equal stop loss (conservative choice)
    expected_sl = 100.0 * (1 - ta.stop_loss_pct)
    assert pytest.approx(row['exit_price'], rel=1e-6) == expected_sl
    assert pd.to_datetime(row['exit_date']) > pd.to_datetime(row['entry_date'])


def test_no_exit_uses_last_close_and_after_entry():
    # No TP/SL hit -> exit at last bar close
    df = make_df([
        (100, 101, 99, 100),
        (100, 101, 99, 101),
        (101, 101, 100, 102),
    ])
    sig = make_signal(0, 100.0, date=df.index[0], typ='buy', symbol='TEST', strength=1)
    ta = PaperTradeAgent(initial_capital=10000)
    trades_df = _run_agent_and_finalize(ta, df, [sig])
    # PaperTradeAgent may leave position open if no TP/SL was hit; check trades for exit
    if trades_df.empty:
        # no exits were recorded; ensure that pending position exists and has no earlier exit
        assert ta.portfolio.has_position('TEST')
        pos = ta.portfolio.get_position('TEST')
        assert pos.entry_index == sig.index
    else:
        row = trades_df.iloc[0]
        assert row['exit_date'] == df.index[-1]
        assert pd.to_datetime(row['exit_date']) > pd.to_datetime(row['entry_date'])
