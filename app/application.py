import os

import matplotlib.pyplot as plt
import streamlit as st
from pandas import DataFrame
from app.agent.signal_generator import SignalGenerator
from app.agent.paper_trade_agent import PaperTradeAgent
from app.strategy.fvgorderblocks import FVGOrderBlocks
from app.strategy.sonarlaplaceorderblocks import SonarlaplaceOrderBlocks
from app.ui.backtest import render_backtest
from app.ui.viewer import render_viewer

# try alternative path if the file layout differs
data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'resource', 'data')
backTest_data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'resource', 'backtest_data')

CSV_FILES = [f for f in os.listdir(data_dir) if f.endswith('.csv')] if os.path.isdir(data_dir) else []
BACK_TEST_CSV_FILES = [f for f in os.listdir(backTest_data_dir) if f.endswith('.csv')] if os.path.isdir(backTest_data_dir) else []


def plot_both_strategies_on_ax(ax: plt.Axes, df: DataFrame, file_name: str):
    """
    Run both strategies and plot them onto the provided Axes.
    Returns tuple (fvg_strategy_instance, sonar_strategy_instance).
    """
    fvg = FVGOrderBlocks()
    fvg.run(df)
    sonar = SonarlaplaceOrderBlocks()
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
    st.title("TradePulse")

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
        render_viewer(CSV_FILES=CSV_FILES, SignalGenerator=SignalGenerator, TradeAgent=PaperTradeAgent, fvg_plotter_fn=plot_both_strategies_on_ax, allocation_params=allocation_params, selected_file=file_name)

    with tabs[1]:
        render_backtest(CSV_FILES=BACK_TEST_CSV_FILES, TradeAgent=PaperTradeAgent, allocation_params=allocation_params)

 


if __name__ == '__main__':
    # Running directly: open Streamlit or print instructions
    if st is None:
        print("Streamlit not detected. Run 'pip install streamlit' and then: streamlit run app/application.py")
    else:
        run_streamlit_app()
