import streamlit as st
import matplotlib.pyplot as plt
import pandas as pd

from app.model import Signal
from app.ui.common import normalize_signals_to_df, get_force_close_at_end
from app.utility.utility import load_data
from app.ui.signal_utils import filter_buy_signals, format_trades_dates
from app.utility.file_util import get_security_name

def render_viewer(CSV_FILES, SignalGenerator, TradeAgent, fvg_plotter_fn, allocation_params, selected_file=None):
    st.header("Viewer")
    if selected_file:
        file_name = selected_file
    else:
        file_name = st.sidebar.selectbox("Select CSV file (Viewer)", options=CSV_FILES, index=0 if CSV_FILES else -1, key='viewer_file')

    if not file_name:
        st.info("No CSV files found in resource/data. Place CSVs under resource/data and reload.")
        return

    # compute rows using provided load_data to avoid direct file path operations
    try:
        rows = len(load_data(file_name))
    except Exception:
        rows = 0

    # Use a single main container (no separate Controls column)
    with st.container():
        # show selected file and rows before the plot controls
        st.markdown(f"**Selected file:** `{file_name}`")
        st.markdown(f"**Rows in file:** {rows}")
        if st.button("Run Simulation"):
            try:
                market_data_df = load_data(file_name)
            except Exception as e:
                st.error(f"Failed to load data: {e}")
                return

            fig, ax = plt.subplots(figsize=(14, 8))
            fvg_strat, sonar_strat = fvg_plotter_fn(ax, market_data_df, file_name)
            st.pyplot(fig)

            try:
                sg = SignalGenerator()
                enhanced_list:list[Signal] = sg.generate_from_file(market_data_df, file_name) or []
            except Exception:
                enhanced_list:list[Signal] = []

            filtered_list = filter_buy_signals(enhanced_list)

            if not filtered_list:
                st.info("No signals with non-zero signalStrength for the selected file.")
                return

            df_display = normalize_signals_to_df(sg, filtered_list)

            # projected shares
            ta_for_calc = TradeAgent(**allocation_params)
            def projected_shares(row):
                try:
                    price = float(row.get('price') or 0)
                    pct = ta_for_calc.allocation_pct(int(row.get('signalStrength') or 0))
                    return int((ta_for_calc.initial_capital * pct) // price) if price > 0 and pct > 0 else 0
                except Exception:
                    return 0

            if not df_display.empty:
                df_display = df_display.copy()
                df_display['projected_shares'] = df_display.apply(projected_shares, axis=1)
                if 'date' in df_display.columns:
                    try:
                        df_display['date'] = pd.to_datetime(df_display['date']).dt.strftime('%Y-%m-%d')
                    except Exception:
                        pass
                # Drop internal / undesired columns before displaying to the user
                display_df = df_display.drop(columns=['index', 'fvg_alpha', 'source_strategy', 'color'], errors='ignore')
                st.subheader("Signals")
                st.dataframe(display_df)

            ta = TradeAgent(**allocation_params)
            try:
                trades_df = ta.execute_signals(market_data_df, filtered_list)
                summary = ta.get_summary()
            except Exception as e:
                st.error(f"Failed to execute signals: {e}")
                return

            # If force-close flag is enabled, force-close remaining open positions for this security
            try:
                if get_force_close_at_end():
                    sec = get_security_name(file_name)
                    ta.force_close_open_positions({sec: market_data_df})
                    ta._process_pending_exits(market_data_df.index[-1])
                    # refresh trades_df and summary
                    trades_df = ta._trades_to_dataframe()
                    summary = ta.get_summary()
            except Exception:
                pass

            if summary is not None:
                st.subheader("Backtest Summary")
                st.table(summary)

            if trades_df is not None and not trades_df.empty:
                st.subheader("Executed Trades")
                tf = format_trades_dates(trades_df)
                st.dataframe(tf)
