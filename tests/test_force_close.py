import pandas as pd
from datetime import datetime, timedelta

from app.agent.paper_trade_agent import PaperTradeAgent
from app.ui.common import set_force_close_at_end, get_force_close_at_end
from app.model.signal import Signal
from app.model.SignalType import SignalType


def make_df(values):
    start = datetime(2025, 1, 1)
    dates = [start + timedelta(days=i) for i in range(len(values))]
    df = pd.DataFrame(values, columns=['Open', 'High', 'Low', 'Close'], index=pd.to_datetime(dates))
    return df


def test_force_close_closes_open_positions():
    # Create data where no TP/SL will be hit after entry at index 0
    df = make_df([
        (100, 101, 99, 100),
        (100, 101, 99, 101),
        (101, 101, 100, 102),
    ])

    sig = Signal(
        index=0,
        price=100.0,
        date=df.index[0],
        type=SignalType.BUY,
        symbol='TEST',
        color=None,
        inside_fvg=False,
        inside_sonar=False,
        fvg_alpha=None,
        signalStrength=1,
        source_strategy=['test']
    )

    # Enable forced close
    prev = get_force_close_at_end()
    set_force_close_at_end(True)
    try:
        ta = PaperTradeAgent(initial_capital=10000)
        trades_df = ta.execute_signals(df, [sig])
        # After execution with forced-close enabled, there should be no open positions
        assert len(ta.portfolio.get_all_positions()) == 0, "Portfolio should have no open positions after forced close"
        # And a trade should have been recorded
        trades = ta._trades_to_dataframe()
        assert not trades.empty, "Trades DataFrame should contain the forced-closed trade"
        # The recorded trade should have security TEST
        assert trades.iloc[0]['security'] == 'TEST'
    finally:
        # restore previous flag state
        set_force_close_at_end(prev)

