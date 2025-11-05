import os
import pandas as pd
import matplotlib.pyplot as plt
from pandas import DataFrame

# Streamlit UI replacement for the previous Tkinter app
try:
    import streamlit as st
except Exception:
    # If streamlit is not available, users will see a helpful message when running the script
    st = None

# Try package imports first (when running as part of package), fall back to local-relative imports
try:
    from app.strategy.fvgorderblocks import FVGOrderBlocks
    from app.strategy.sonarlaborderblocks import SonarlabOrderBlocks
    from app.utility.utility import load_data
    from app.agent.signal_generator import SignalGenerator
    from app.agent.trade_agent import TradeAgent
    from app.ui.viewer import render_viewer
    from app.ui.backtest import render_backtest
except Exception:
    # running as a script (python app/application.py) - import from local module names
    from strategy.fvgorderblocks import FVGOrderBlocks
    from strategy.sonarlaborderblocks import SonarlabOrderBlocks
    from utility.utility import load_data
    from agent.signal_generator import SignalGenerator
    from agent.trade_agent import TradeAgent
    from ui.viewer import render_viewer
    from ui.backtest import render_backtest

    # try alternative path if the file layout differs
data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'resource', 'data')

CSV_FILES = [f for f in os.listdir(data_dir) if f.endswith('.csv')] if os.path.isdir(data_dir) else []


def plot_both_strategies_on_ax(ax: plt.Axes, df: DataFrame, file_name: str):
    """
    Run both strategies and plot them onto the provided Axes.
    Returns tuple (fvg_strategy_instance, sonar_strategy_instance).
    """
    fvg = FVGOrderBlocks()
    fvg.run(df)
    sonar = SonarlabOrderBlocks()
    sonar.run(df)

    # Draw candles once and let each strategy overlay its visuals on the given axes
    try:
        fvg.plot(df, title=f"Combined Order Blocks [{file_name}]", ax=ax)
    except TypeError:
        # Some plot implementations expect different args; call without title
        fvg.plot(df, ax=ax)
    try:
        sonar.plot(df, ax=ax)
    except Exception:
        # ignore plotting errors from the second strategy
        pass
    return fvg, sonar


def run_streamlit_app():
    """Main Streamlit app. Presents two tabs: Viewer and Back Test."""
    if st is None:
        print("Streamlit is not installed. Install with: pip install streamlit")
        return

    st.set_page_config(page_title="TradePulse Viewer", layout="wide")
    st.title("TradePulse Order Blocks Viewer (Streamlit)")

    # Sidebar file selection and backtest controls
    st.sidebar.header("Data / Controls")
    file_name = st.sidebar.selectbox("Select CSV file", options=CSV_FILES, index=0 if CSV_FILES else -1, key='main_file')

    st.sidebar.subheader("Backtest Parameters")
    initial_capital = st.sidebar.number_input("Initial Capital", min_value=100.0, value=100000.0, step=100.0, format="%.2f")
    target_pct = st.sidebar.slider("Target %", min_value=0.0, max_value=1.0, value=0.07, step=0.01, format="%.2f")
    stop_loss_pct = st.sidebar.slider("Stop Loss %", min_value=0.0, max_value=1.0, value=0.03, step=0.01, format="%.2f")
    allocation_step = st.sidebar.slider("Allocation per Strength Unit (fraction)", min_value=0.01, max_value=1.0, value=0.2, step=0.01, format="%.2f")

    tabs = st.tabs(["Viewer", "Back Test"])

    # prepare allocation params
    allocation_params = {
        'initial_capital': initial_capital,
        'target_pct': target_pct,
        'stop_loss_pct': stop_loss_pct,
        'allocation_step': allocation_step
    }

    # render viewer/backtest inside tabs
    with tabs[0]:
        render_viewer(CSV_FILES=CSV_FILES, data_dir=data_dir, load_data=load_data, SignalGenerator=SignalGenerator, TradeAgent=TradeAgent, fvg_plotter_fn=plot_both_strategies_on_ax, allocation_params=allocation_params, selected_file=file_name)

    with tabs[1]:
        render_backtest(CSV_FILES=CSV_FILES, data_dir=data_dir, load_data=load_data, SignalGenerator=SignalGenerator, TradeAgent=TradeAgent, allocation_params=allocation_params, selected_file=file_name)

    # # Viewer tab: show plot, signals and executed trades summary
    # with tabs[0]:
    #     st.header("Single")
    #     if not file_name:
    #         st.info("No CSV files found in resource/data. Place CSVs under resource/data and reload.")
    #     else:
    #         col1, col2 = st.columns([3, 1])
    #         with col1:
    #             st.subheader("Price Chart + Strategy Overlays")
    #             if st.button("Plot Graph"):
    #                 try:
    #                     market_data_df = load_data(file_name)
    #                 except Exception as e:
    #                     st.error(f"Failed to load data: {e}")
    #                     market_data_df = None

    #                 if market_data_df is not None:
    #                     fig, ax = plt.subplots(figsize=(14, 8))
    #                     fvg_strat, sonar_strat = plot_both_strategies_on_ax(ax, market_data_df, file_name)
    #                     st.pyplot(fig)

    #                     # Gather signals from strategies and SignalGenerator
    #                     enhanced_list = []
    #                     try:
    #                         sg = SignalGenerator()
    #                         enhanced_list = sg.generate_from_file(market_data_df) or []
    #                     except Exception:
    #                         enhanced_list = []

    #                     filtered_list = [e for e in enhanced_list if getattr(e, 'signalStrength', 0) != 0]

    #                     # Show signals and projected shares
    #                     if not filtered_list:
    #                         st.info("No signals with non-zero signalStrength for the selected file.")
    #                     else:
    #                         try:
    #                             df_display = sg.to_dataframe(filtered_list)
    #                         except Exception:
    #                             # fallback: build a simple dataframe
    #                             rows = []
    #                             for s in filtered_list:
    #                                 rows.append({
    #                                     'date': getattr(s, 'date', None),
    #                                     'price': getattr(s, 'price', None),
    #                                     'type': getattr(s, 'type', None),
    #                                     'signalStrength': getattr(s, 'signalStrength', None)
    #                                 })
    #                             df_display = pd.DataFrame(rows)

    #                         # compute projected shares using TradeAgent allocation logic with sidebar params
    #                         ta_for_calc = TradeAgent(initial_capital=initial_capital, target_pct=target_pct, stop_loss_pct=stop_loss_pct, allocation_step=allocation_step)
    #                         def projected_shares(row):
    #                             try:
    #                                 price = float(row.get('price') or 0)
    #                                 pct = ta_for_calc.allocation_pct(int(row.get('signalStrength') or 0))
    #                                 return int((ta_for_calc.initial_capital * pct) // price) if price > 0 and pct > 0 else 0
    #                             except Exception:
    #                                 return 0

    #                         if not df_display.empty:
    #                             df_display = df_display.copy()
    #                             df_display['projected_shares'] = df_display.apply(projected_shares, axis=1)
    #                             # normalize date column if present
    #                             if 'date' in df_display.columns:
    #                                 try:
    #                                     df_display['date'] = pd.to_datetime(df_display['date']).dt.strftime('%Y-%m-%d')
    #                                 except Exception:
    #                                     pass
    #                             st.subheader("Signals (projected shares based on allocation)")
    #                             st.dataframe(df_display)

    #                         # Execute signals through TradeAgent and show summary/trades
    #                         ta = TradeAgent(initial_capital=initial_capital, target_pct=target_pct, stop_loss_pct=stop_loss_pct, allocation_step=allocation_step)
    #                         try:
    #                             trades_df = ta.execute_signals(market_data_df, filtered_list)
    #                             summary = ta.get_summary()
    #                         except Exception as e:
    #                             st.error(f"Failed to execute signals: {e}")
    #                             trades_df = None
    #                             summary = None

    #                         if summary is not None:
    #                             st.subheader("Backtest Summary")
    #                             try:
    #                                 # Try to show as table of metric/value
    #                                 if isinstance(summary, dict):
    #                                     summary_df = pd.DataFrame(list(summary.items()), columns=['metric', 'value'])
    #                                     st.table(summary_df)
    #                                 else:
    #                                     st.write(summary)
    #                             except Exception:
    #                                 st.write(summary)

    #                         if trades_df is not None and not trades_df.empty:
    #                             st.subheader("Executed Trades")
    #                             # ensure dates are readable
    #                             tf = trades_df.copy()
    #                             for c in ['entry_date', 'exit_date']:
    #                                 if c in tf.columns:
    #                                     try:
    #                                         tf[c] = pd.to_datetime(tf[c]).dt.strftime('%Y-%m-%d')
    #                                     except Exception:
    #                                         pass
    #                             st.dataframe(tf)
    #         with col2:
    #             st.subheader("Controls")
    #             st.write(f"Selected file: {file_name}")
    #             st.write(f"Rows in file: {len(pd.read_csv(os.path.join(data_dir, file_name))) if file_name else 0}")
    #             st.write("---")
    #             st.write("Backtest parameters currently in use:")
    #             st.write({
    #                 'initial_capital': initial_capital,
    #                 'target_pct': target_pct,
    #                 'stop_loss_pct': stop_loss_pct,
    #                 'allocation_step': allocation_step
    #             })

    # # Back Test tab: a simple runner that shows summary/trades when clicking Run Backtest
    # with tabs[1]:
    #     st.header("Back Test")
    #     st.write("Run the same signal -> execute pipeline and view summary + trades.")
    #     if not file_name:
    #         st.info("No CSV selected.")
    #     else:
    #         if st.button("Run Backtest"):
    #             try:
    #                 market_data_df = load_data(file_name)
    #             except Exception as e:
    #                 st.error(f"Failed to load data: {e}")
    #                 market_data_df = None

    #             if market_data_df is not None:
    #                 # generate enhanced signals
    #                 enhanced_list = []
    #                 try:
    #                     sg = SignalGenerator()
    #                     enhanced_list = sg.generate_from_file(market_data_df) or []
    #                 except Exception:
    #                     enhanced_list = []

    #                 filtered_list = [e for e in enhanced_list if getattr(e, 'signalStrength', 0) != 0]

    #                 if not filtered_list:
    #                     st.info("No signals with non-zero strength found for the selected file.")
    #                 else:
    #                     ta = TradeAgent(initial_capital=initial_capital, target_pct=target_pct, stop_loss_pct=stop_loss_pct, allocation_step=allocation_step)
    #                     try:
    #                         trades_df = ta.execute_signals(market_data_df, filtered_list)
    #                         summary = ta.get_summary()
    #                     except Exception as e:
    #                         st.error(f"Failed to run backtest: {e}")
    #                         trades_df = None
    #                         summary = None

    #                     if summary is not None:
    #                         st.subheader("Backtest Summary")
    #                         try:
    #                             if isinstance(summary, dict):
    #                                 summary_df = pd.DataFrame(list(summary.items()), columns=['metric', 'value'])
    #                                 st.table(summary_df)
    #                             else:
    #                                 st.write(summary)
    #                         except Exception:
    #                             st.write(summary)

    #                     if trades_df is not None and not trades_df.empty:
    #                         st.subheader("Trades")
    #                         tf = trades_df.copy()
    #                         for c in ['entry_date', 'exit_date']:
    #                             if c in tf.columns:
    #                                 try:
    #                                     tf[c] = pd.to_datetime(tf[c]).dt.strftime('%Y-%m-%d')
    #                                 except Exception:
    #                                     pass
    #                         st.dataframe(tf)


if __name__ == '__main__':
    # Running directly: open Streamlit or print instructions
    if st is None:
        print("Streamlit not detected. Run 'pip install streamlit' and then: streamlit run app/application.py")
    else:
        run_streamlit_app()
