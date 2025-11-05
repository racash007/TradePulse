import sys, os
# add project root to sys.path
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

from app.strategy.signal_generator import SignalGenerator
from app.strategy.trade_agent import TradeAgent

sg = SignalGenerator()
# load DataFrame using the generator helper (accepts filter or path)
df = sg._read_csv_into_df('ABB')
enh = sg.generate_from_file(df)
filtered = [e for e in enh if getattr(e, 'signalStrength', 0) != 0]
print('Enhanced total:', len(enh))
print('Filtered non-zero:', len(filtered))
if filtered:
    ta = TradeAgent()
    trades = ta.execute_signals(df, filtered)
    print('\nSummary:')
    summary = ta.get_summary()
    for k, v in summary.items():
        print(f"{k}: {v}")
    print('\nTrades sample:')
    if not trades.empty:
        print(trades.head().to_string(index=False))
    else:
        print('No trades executed')
else:
    print('No filtered signals to execute')
