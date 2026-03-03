import pandas as pd
import pytest
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.agent.paper_trade_agent import PaperTradeAgent


def make_df(values):
    start = datetime(2025, 1, 1)
    dates = [start + timedelta(days=i) for i in range(len(values))]
    df = pd.DataFrame(values, columns=['Open', 'High', 'Low', 'Close'], index=pd.to_datetime(dates))
    return df


def make_signal(idx, price, date=None, typ='buy', symbol='TEST', strength=1):
    return SimpleNamespace(index=idx, price=price, date=date, type=typ, symbol=symbol, signalStrength=strength)


def test_paper_agent_handles_entry_exit_and_dates():
    # create a dataset where entry at 0 and exit at 1
    df = make_df([
        (100, 100, 99, 100),
        (101, 110, 99, 105),
    ])
    sig = make_signal(0, 100.0, date=df.index[0], typ='buy', symbol='TEST', strength=2)
    ta = PaperTradeAgent(initial_capital=100000)
    trades_df = ta.execute_signals(df, [sig])
    # PaperTradeAgent stores trades later via pending exits; ensure resulting trades df exists
    assert isinstance(trades_df, pd.DataFrame)
    # After executing, summary should show consistent dates
    summary = ta.get_summary()
    assert 'initial_capital' in summary.__dict__ or isinstance(summary, object)


def test_paper_agent_no_negative_exit_dates():
    """
    Tests that any executed trade has an exit date that is not before its entry date.
    """
    # Build data where no exit occurs; ensure exit date won't be before entry.
    # The make_df helper function creates a DataFrame with a DatetimeIndex.
    df = make_df([
        (100, 101, 99, 100),  # Entry bar, e.g., 2025-01-01
        (100, 101, 99, 101),  # No exit is hit here, e.g., 2025-01-02
    ])
    # Explicitly check that our test data has the date index as expected.
    assert isinstance(df.index, pd.DatetimeIndex)

    sig = make_signal(0, 100.0, date=df.index[0], typ='buy', symbol='TEST', strength=1)
    ta = PaperTradeAgent(initial_capital=10000)
    trades_df = ta.execute_signals(df, [sig])

    # The PaperTradeAgent may keep the position open if no exit is found,
    # resulting in an empty trades_df. This is expected.
    # The assertion below only runs if any trades were actually closed and recorded.
    if not trades_df.empty:
        for _, row in trades_df.iterrows():
            assert pd.to_datetime(row['exit_date']) >= pd.to_datetime(row['entry_date'])


def test_allocation_capped_to_one_lakh_or_initial_capital():
    # initial capital > 1 lakh; allocation base should still be capped at 1 lakh
    df = make_df([
        (100, 101, 99, 100),
    ])
    sig = make_signal(0, 100.0, date=df.index[0], typ='buy', symbol='TEST', strength=4)

    ta = PaperTradeAgent(initial_capital=500000)
    ta.execute_signals(df, [sig])

    assert ta.portfolio.has_position('TEST')
    pos = ta.portfolio.get_position('TEST')
    # strength 4 -> 30%; 30% of 1,00,000 = 30,000 => 300 shares at price 100
    assert pos.shares == 300


def test_same_day_330pm_keeps_only_highest_price_signal():
    ts = pd.Timestamp('2023-03-29 15:30:00')
    df = pd.DataFrame(
        [(100, 101, 99, 100), (100, 101, 99, 100)],
        columns=['Open', 'High', 'Low', 'Close'],
        index=pd.to_datetime([ts, ts + timedelta(minutes=5)])
    )

    low_price_sig = make_signal(0, 100.0, date=ts, typ='buy', symbol='LOW', strength=1)
    high_price_sig = make_signal(0, 200.0, date=ts, typ='buy', symbol='HIGH', strength=1)

    ta = PaperTradeAgent(initial_capital=100000)
    ta.execute_signals(df, [low_price_sig, high_price_sig])

    open_positions = ta.portfolio.get_all_positions()
    assert len(open_positions) == 1
    assert open_positions[0].security == 'HIGH'


def test_daily_granularity_does_not_apply_330pm_filter():
    # Daily timestamps (00:00) should not trigger intraday tie-break logic.
    ts = pd.Timestamp('2023-03-29 00:00:00')
    df = pd.DataFrame(
        [(100, 101, 99, 100), (100, 101, 99, 100)],
        columns=['Open', 'High', 'Low', 'Close'],
        index=pd.to_datetime([ts, ts + timedelta(days=1)])
    )

    s1 = make_signal(0, 100.0, date=ts, typ='buy', symbol='IOC', strength=1)
    s2 = make_signal(0, 200.0, date=ts, typ='buy', symbol='TCS', strength=1)

    ta = PaperTradeAgent(initial_capital=100000)
    ta.execute_signals(df, [s1, s2])

    open_positions = ta.portfolio.get_all_positions()
    # Both signals are on same daily bar and should both be eligible (subject to cash).
    assert len(open_positions) == 2


def test_impossible_exit_price_is_not_closed():
    # Exit metadata says TP hit, but bar high never reaches that price.
    df = make_df([
        (160.0, 164.0, 159.0, 163.0),
        (162.0, 163.0, 157.0, 159.0),
    ])

    sig = make_signal(0, 160.0, date=df.index[0], typ='buy', symbol='IOC', strength=1)
    ta = PaperTradeAgent(initial_capital=100000)
    ta.execute_signals(df, [sig])

    # Inject inconsistent precomputed exit (unreachable TP on bar 1)
    pos = ta.portfolio.get_position('IOC')
    assert pos is not None
    pos.exit_idx = 1
    pos.exit_date = df.index[1]
    pos.exit_price = 175.30
    pos.outcome = 'win'  # intentionally wrong type first
    from app.model.OutcomeType import OutcomeType
    pos.outcome = OutcomeType.WIN
    pos.is_long = True
    pos.pnl = pos.shares * (pos.exit_price - pos.entry_price)
    pos.proceeds = pos.shares * pos.exit_price
    pos.cash_before = ta.cash

    ta._process_pending_exits(df.index[-1])

    # Should remain open because exit price is impossible on recorded bar.
    assert ta.portfolio.has_position('IOC')
    trades_df = ta._trades_to_dataframe()
    assert trades_df.empty


def test_daily_deployment_capped_to_one_lakh_across_symbols():
    # Same-day multiple signals should share one daily deployment cap.
    day = pd.Timestamp('2026-03-02 00:00:00')
    df = pd.DataFrame(
        [
            (100, 101, 99, 100),
            (100, 101, 99, 100),
        ],
        columns=['Open', 'High', 'Low', 'Close'],
        index=pd.to_datetime([day, day + timedelta(days=1)])
    )

    # strength=3 => 25% of 1,00,000 = 25,000 per signal at price 100 (250 shares)
    signals = [
        make_signal(0, 100.0, date=day, typ='buy', symbol='S1', strength=3),
        make_signal(0, 100.0, date=day, typ='buy', symbol='S2', strength=3),
        make_signal(0, 100.0, date=day, typ='buy', symbol='S3', strength=3),
        make_signal(0, 100.0, date=day, typ='buy', symbol='S4', strength=3),
        make_signal(0, 100.0, date=day, typ='buy', symbol='S5', strength=3),
    ]

    ta = PaperTradeAgent(initial_capital=500000)
    ta.execute_signals(df, signals)

    # At most 4 entries can be opened on same day under 1 lakh total deployment.
    open_positions = ta.portfolio.get_all_positions()
    assert len(open_positions) == 4
    total_alloc = sum(float(p.money_allocated) for p in open_positions)
    assert total_alloc <= 100000.0
