import streamlit as st
import matplotlib.pyplot as plt
import pandas as pd
import matplotlib.dates as mdates

from model import Signal, SignalType, Box
from ui.common import normalize_signals_to_df, get_force_close_at_end
from utility.utility import load_data, atr_series
from ui.signal_utils import filter_buy_signals, format_trades_dates
from utility.file_util import get_security_name
from utility.plot_utils import draw_candlesticks, draw_boxes, draw_signals, setup_chart_axes


def _index_from_date(df: pd.DataFrame, date_value) -> int | None:
    if date_value is None or (isinstance(date_value, float) and pd.isna(date_value)):
        return None
    try:
        ts = pd.to_datetime(date_value)
    except Exception:
        return None
    try:
        if ts in df.index:
            return int(df.index.get_loc(ts))
        idx = df.index.get_indexer([ts], method='nearest')[0]
        return int(idx) if idx >= 0 else None
    except Exception:
        return None


def _subset_boxes(boxes: list[Box], start_idx: int, end_idx: int) -> list[Box]:
    sliced: list[Box] = []
    for box in boxes or []:
        if box.right < start_idx or box.left > end_idx:
            continue
        new_left = max(box.left, start_idx) - start_idx
        new_right = min(box.right, end_idx) - start_idx
        sliced.append(Box(
            left=new_left,
            right=new_right,
            top=box.top,
            bottom=box.bottom,
            box_type=box.box_type,
            alpha=box.alpha,
            border_color=box.border_color,
            bg_color=box.bg_color,
            border_width=box.border_width,
            broken=box.broken,
            percent=box.percent,
            created_at=box.created_at
        ))
    return sliced


def _build_trade_signals(entry_idx: int | None, exit_idx: int | None, entry_price: float | None,
                         exit_price: float | None, trade_side) -> list[Signal]:
    signals: list[Signal] = []
    if entry_idx is not None and entry_price is not None:
        entry_type = SignalType.BUY if str(trade_side).lower() == 'buy' else SignalType.SELL
        signals.append(Signal(
            index=entry_idx,
            price=float(entry_price),
            date=None,
            type=entry_type,
            symbol='E',
            color='#1f77b4',
            inside_fvg=False,
            inside_sonar=False,
            fvg_alpha=None,
            signalStrength=0,
            source_strategy=['TradeEntry']
        ))
    if exit_idx is not None and exit_price is not None:
        exit_type = SignalType.SELL if str(trade_side).lower() == 'buy' else SignalType.BUY
        signals.append(Signal(
            index=exit_idx,
            price=float(exit_price),
            date=None,
            type=exit_type,
            symbol='X',
            color='#ff7f0e',
            inside_fvg=False,
            inside_sonar=False,
            fvg_alpha=None,
            signalStrength=0,
            source_strategy=['TradeExit']
        ))
    return signals

def render_viewer(CSV_FILES, SignalGenerator, TradeAgent, fvg_plotter_fn, allocation_params, selected_file=None, min_signal_strength: int = 1):
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

            filtered_list = filter_buy_signals(enhanced_list, min_signal_strength)

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

                st.subheader("Trade Visualizations")
                show_trade_charts = st.checkbox("Show trade visualizations", value=True)
                if show_trade_charts:
                    bars_padding = st.slider("Bars before/after trade", min_value=10, max_value=250, value=60, step=10)
                    max_trades = st.number_input("Max trades to render", min_value=1, max_value=100, value=20, step=1)

                    atr_full = atr_series(market_data_df, period=14)
                    total_rows = len(market_data_df)
                    trades_to_render = trades_df.head(int(max_trades))

                    for trade_num, (_, trade_row) in enumerate(trades_to_render.iterrows(), start=1):
                        entry_idx = None
                        if 'entry_index' in trade_row and pd.notna(trade_row['entry_index']):
                            try:
                                entry_idx = int(trade_row['entry_index'])
                            except Exception:
                                entry_idx = None
                        if entry_idx is None:
                            entry_idx = _index_from_date(market_data_df, trade_row.get('entry_date'))

                        exit_idx = _index_from_date(market_data_df, trade_row.get('exit_date'))

                        if entry_idx is None and exit_idx is None:
                            continue

                        entry_price = trade_row.get('entry_price')
                        exit_price = trade_row.get('exit_price')
                        if entry_price is not None and pd.isna(entry_price):
                            entry_price = None
                        if exit_price is not None and pd.isna(exit_price):
                            exit_price = None
                        trade_side = trade_row.get('side')

                        trade_start = entry_idx if entry_idx is not None else exit_idx
                        trade_end = exit_idx if exit_idx is not None else entry_idx
                        if trade_start is None or trade_end is None:
                            continue

                        start_idx = max(0, min(trade_start, trade_end) - bars_padding)
                        end_idx = min(total_rows - 1, max(trade_start, trade_end) + bars_padding)
                        df_slice = market_data_df.iloc[start_idx:end_idx + 1]

                        entry_local = entry_idx - start_idx if entry_idx is not None else None
                        exit_local = exit_idx - start_idx if exit_idx is not None else None

                        signals = _build_trade_signals(entry_local, exit_local, entry_price, exit_price, trade_side)

                        fvg_boxes = []
                        if fvg_strat is not None:
                            fvg_boxes = _subset_boxes(
                                (fvg_strat.bull_boxes or []) + (fvg_strat.bear_boxes or []),
                                start_idx,
                                end_idx
                            )

                        sonar_boxes = []
                        if sonar_strat is not None:
                            sonar_boxes = _subset_boxes(
                                (sonar_strat.long_boxes or []) + (sonar_strat.short_boxes or []),
                                start_idx,
                                end_idx
                            )

                        with st.expander(f"Trade {trade_num} ({trade_side})"):
                            fig, (ax_price, ax_atr) = plt.subplots(
                                2,
                                1,
                                figsize=(14, 8),
                                sharex=True,
                                gridspec_kw={'height_ratios': [3, 1]}
                            )

                            draw_candlesticks(ax_price, df_slice)
                            draw_boxes(ax_price, fvg_boxes, list(df_slice.index))
                            draw_boxes(ax_price, sonar_boxes, list(df_slice.index))
                            draw_signals(ax_price, signals, list(df_slice.index))
                            setup_chart_axes(ax_price, title=f"Trade {trade_num} ({trade_side})")

                            atr_slice = atr_full.iloc[start_idx:end_idx + 1]
                            ax_atr.plot([mdates.date2num(d) for d in df_slice.index], atr_slice.values, color='#6a51a3', linewidth=1.2)
                            ax_atr.set_ylabel("ATR(14)")
                            ax_atr.grid(True, linestyle='--', linewidth=0.5, alpha=0.4)

                            st.pyplot(fig)
