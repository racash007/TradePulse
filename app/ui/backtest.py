import pandas as pd
import streamlit as st
from utility.utility import load_data

def render_backtest(CSV_FILES, SignalGenerator, TradeAgent, allocation_params, selected_file=None):
    st.header("Back Test")
    if selected_file:
        file_name = selected_file
    else:
        file_name = st.sidebar.selectbox("Select CSV file for Backtest", options=CSV_FILES, index=0 if CSV_FILES else -1, key='backtest_file')
    st.write("Run the same signal -> execute pipeline and view summary + trades.")
    if not file_name:
        st.info("No CSV selected.")
        return

    if st.button("Run Backtest"):
        try:
            market_data_df = load_data(file_name)
        except Exception as e:
            st.error(f"Failed to load data: {e}")
            return

        # generate enhanced signals
        enhanced_list = []
        try:
            sg = SignalGenerator()
            enhanced_list = sg.generate_from_file(market_data_df) or []
        except Exception:
            enhanced_list = []

        filtered_list = [e for e in enhanced_list if getattr(e, 'signalStrength', 0) != 0]

        if not filtered_list:
            st.info("No signals with non-zero strength found for the selected file.")
            return

        ta = TradeAgent(**allocation_params)
        try:
            trades_df = ta.execute_signals(market_data_df, filtered_list)
            summary = ta.get_summary()
        except Exception as e:
            st.error(f"Failed to run backtest: {e}")
            return

        if summary is not None:
            st.subheader("Backtest Summary")
            if isinstance(summary, dict):
                summary_df = pd.DataFrame(list(summary.items()), columns=['metric', 'value'])
                st.table(summary_df)
            else:
                st.write(summary)

        if trades_df is not None and not trades_df.empty:
            st.subheader("Trades")
            tf = trades_df.copy()
            for c in ['entry_date', 'exit_date']:
                if c in tf.columns:
                    try:
                        tf[c] = pd.to_datetime(tf[c]).dt.strftime('%Y-%m-%d')
                    except Exception:
                        pass
            st.dataframe(tf)
