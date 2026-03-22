"""
Backtest UI component for running strategy backtests.
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional, Any
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from model.signal import Signal
from model import SignalType, Box
from utility.utility import load_data, atr_series
from utility.file_util import get_security_name
from agent.signal_generator import get_signal_generator
from ui.signal_utils import filter_buy_signals, format_trades_dates, format_numeric_columns
from ui.common import set_force_close_at_end, get_force_close_at_end
from ui.optimizer import BacktestOptimizer
from strategy.fvgorderblocks import FVGOrderBlocks
from strategy.sonarlaplaceorderblocks import SonarlaplaceOrderBlocks
from utility.plot_utils import draw_candlesticks, draw_boxes, draw_signals, setup_chart_axes

# Absolute path to the stock database (project_root/resource/stock_data.db)
_DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'resource', 'stock_data.db',
)


def load_symbols_from_db(db_path=None):
    """Load available symbols from database."""
    if db_path is None:
        db_path = _DEFAULT_DB_PATH
    try:
        conn = sqlite3.connect(db_path)
        query = """
            SELECT DISTINCT symbol, COUNT(*) as count
            FROM stock_data
            GROUP BY symbol
            HAVING count >= 100
            ORDER BY symbol
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df['symbol'].tolist()
    except Exception as e:
        st.error(f"Error loading symbols from database: {e}")
        return []


def load_data_from_db(symbol, db_path=None, start_date=None, end_date=None):
    """Load OHLCV data for a symbol from database."""
    if db_path is None:
        db_path = _DEFAULT_DB_PATH
    try:
        conn = sqlite3.connect(db_path)
        
        query = """
            SELECT datetime, open, high, low, close, volume
            FROM stock_data
            WHERE symbol = ?
        """
        params = [symbol]
        
        if start_date:
            query += " AND datetime >= ?"
            params.append(start_date.strftime('%Y-%m-%d'))
        
        if end_date:
            query += " AND datetime <= ?"
            params.append(end_date.strftime('%Y-%m-%d'))
        
        query += " ORDER BY datetime"
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        if not df.empty:
            df['datetime'] = pd.to_datetime(df['datetime'])
            # Remove timezone info to avoid comparison issues
            if hasattr(df['datetime'].dt, 'tz') and df['datetime'].dt.tz is not None:
                df['datetime'] = df['datetime'].dt.tz_localize(None)
            df.set_index('datetime', inplace=True)
            df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        
        return df
    except Exception as e:
        st.error(f"Error loading data for {symbol}: {e}")
        return pd.DataFrame()


def render_backtest(CSV_FILES, TradeAgent, allocation_params, min_signal_strength: int = 1):
    """Render the backtest UI and execute backtests."""
    st.subheader("Backtest Configuration")
    
    # Data source selection
    data_source = st.radio("Data Source", ["CSV Files", "Database"], horizontal=True)
    
    if data_source == "Database":
        _render_database_backtest(TradeAgent, allocation_params, min_signal_strength)
    else:
        _render_csv_backtest(CSV_FILES, TradeAgent, allocation_params, min_signal_strength)


def _render_database_backtest(TradeAgent, allocation_params, min_signal_strength: int):
    """Render database-based backtest UI."""
    db_path = st.text_input("Database Path", value=_DEFAULT_DB_PATH)
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Date range selection
        st.markdown("**Date Range**")
        use_all_data = st.checkbox("Use all available data", value=True)
        
        if not use_all_data:
            start_date = st.date_input("Start Date", value=datetime.now() - timedelta(days=365))
            end_date = st.date_input("End Date", value=datetime.now())
        else:
            start_date = None
            end_date = None
    
    with col2:
        # Symbol selection
        st.markdown("**Symbol Selection**")
        symbols = load_symbols_from_db(db_path)
        
        if symbols:
            st.info(f"Found {len(symbols)} symbols in database")
            use_all_symbols = st.checkbox("Test all symbols", value=False)
            
            if not use_all_symbols:
                selected_symbols = st.multiselect("Select symbols", options=symbols, default=symbols[:5])
            else:
                selected_symbols = symbols
        else:
            st.error("No symbols found in database")
            return
    
    # Optimization mode
    st.markdown("**Backtest Mode**")
    mode = st.radio("Mode", ["Single Run", "Optimize Parameters"], horizontal=True)
    
    if mode == "Optimize Parameters":
        _render_optimizer_ui(TradeAgent, allocation_params, selected_symbols, db_path, start_date, end_date)
    else:
        # Checkbox to toggle forced close
        force_close = st.checkbox("Force close open positions at end of data", value=get_force_close_at_end())
        set_force_close_at_end(bool(force_close))
        
        if st.button("Run Backtest"):
            with st.spinner(f"Running backtest on {len(selected_symbols)} symbols..."):
                results = _run_database_backtest(selected_symbols, db_path, start_date, end_date, TradeAgent, allocation_params, min_signal_strength)
                if results:
                    summary, trades_df, portfolio, data_dict = results
                    st.session_state['backtest_results'] = {
                        'summary': summary,
                        'trades_df': trades_df,
                        'portfolio': portfolio,
                        'data_dict': data_dict
                    }

        # Display last results (persisted across reruns)
        if 'backtest_results' in st.session_state:
            stored = st.session_state.get('backtest_results') or {}
            _display_results(
                stored.get('summary'),
                stored.get('trades_df'),
                stored.get('portfolio'),
                stored.get('data_dict')
            )


def _render_optimizer_ui(TradeAgent, allocation_params, selected_symbols, db_path, start_date, end_date):
    """Render optimizer configuration UI."""
    st.markdown("**Parameter Ranges to Test**")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("*Risk-Reward Ratios*")
        rr_min = st.number_input("Min RR", min_value=1.0, max_value=10.0, value=1.8, step=0.1)
        rr_max = st.number_input("Max RR", min_value=1.0, max_value=10.0, value=5.0, step=0.1)
        rr_step = st.number_input("RR Step", min_value=0.1, max_value=2.0, value=0.5, step=0.1)
        
    with col2:
        st.markdown("*Stop Loss %*")
        sl_values = st.multiselect("Stop Loss %", options=[0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08], default=[0.03, 0.04, 0.05])
        
    with col3:
        st.markdown("*Allocation Steps*")
        alloc_values = st.multiselect("Allocation Steps", options=[0.10, 0.15, 0.20, 0.25, 0.30], default=[0.15, 0.20, 0.25])
    
    # Calculate parameter combinations
    import numpy as np
    rr_ratios = list(np.arange(rr_min, rr_max + rr_step/2, rr_step))
    total_combinations = len(rr_ratios) * len(sl_values) * len(alloc_values)
    
    st.info(f"Will test **{total_combinations}** parameter combinations on **{len(selected_symbols)}** symbols")
    st.warning(f"Estimated time: ~{total_combinations * 0.5:.0f} seconds ({total_combinations * 0.5 / 60:.1f} minutes)")
    
    force_close = st.checkbox("Force close open positions at end of data", value=True)
    set_force_close_at_end(bool(force_close))
    
    if st.button("Run Optimization", type="primary"):
        param_ranges = {
            'risk_reward_ratio': rr_ratios,
            'stop_loss_pct': sl_values,
            'allocation_step': alloc_values,
            'initial_capital': [allocation_params.get('initial_capital', 100000.0)]
        }
        
        with st.spinner(f"Running optimization... This may take several minutes."):
            _run_optimizer(selected_symbols, db_path, start_date, end_date, TradeAgent, param_ranges)


def _run_optimizer(selected_symbols, db_path, start_date, end_date, TradeAgent, param_ranges):
    """Run backtest optimizer."""
    # Load data for all symbols
    data_dict = {}
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, symbol in enumerate(selected_symbols):
        status_text.text(f"Loading data: {symbol} ({i+1}/{len(selected_symbols)})")
        df = load_data_from_db(symbol, db_path, start_date, end_date)
        if not df.empty:
            data_dict[symbol] = df
        progress_bar.progress((i + 1) / len(selected_symbols))
    
    if not data_dict:
        st.error("No data loaded for selected symbols")
        return
    
    status_text.text(f"Loaded data for {len(data_dict)} symbols. Starting optimization...")
    
    # Run optimization
    sg = get_signal_generator()
    optimizer = BacktestOptimizer(
        data_dict=data_dict,
        strategy_class=FVGOrderBlocks,
        trade_agent_class=TradeAgent,
        signal_generator=sg
    )
    
    results_df = optimizer.optimize(param_ranges=param_ranges, metric='total_pnl', max_workers=1)
    
    progress_bar.empty()
    status_text.empty()
    
    # Display results
    st.success("Optimization complete!")
    
    st.markdown("### Top 10 Parameter Combinations")
    display_cols = [
        'risk_reward_ratio', 'stop_loss_pct', 'allocation_step',
        'total_pnl', 'total_return_pct', 'win_rate', 'profit_factor',
        'total_trades', 'max_drawdown_pct', 'sharpe_ratio'
    ]
    display_cols = [col for col in display_cols if col in results_df.columns]
    
    st.dataframe(results_df.head(10)[display_cols], use_container_width=True)
    
    # Best parameters
    best = results_df.iloc[0]
    st.markdown("### Best Parameters")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Risk-Reward Ratio", f"{best.get('risk_reward_ratio', 0):.2f}")
        st.metric("Stop Loss %", f"{best.get('stop_loss_pct', 0):.2%}")
        st.metric("Allocation Step", f"{best.get('allocation_step', 0):.2f}")
    
    with col2:
        st.metric("Total P&L", f"₹{best.get('total_pnl', 0):,.2f}")
        st.metric("Total Return", f"{best.get('total_return_pct', 0):.2f}%")
        st.metric("Win Rate", f"{best.get('win_rate', 0):.2f}%")
    
    with col3:
        st.metric("Profit Factor", f"{best.get('profit_factor', 0):.2f}")
        st.metric("Total Trades", f"{best.get('total_trades', 0):.0f}")
        st.metric("Max Drawdown", f"{best.get('max_drawdown_pct', 0):.2f}%")
    
    # Download results
    csv = results_df.to_csv(index=False)
    st.download_button(
        label="Download Full Results (CSV)",
        data=csv,
        file_name=f"optimization_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )


def _run_database_backtest(selected_symbols, db_path, start_date, end_date, TradeAgent, allocation_params, min_signal_strength: int) -> Optional[Tuple[Any, pd.DataFrame, Any, dict]]:
    """Run backtest using database data."""
    # Load data for all symbols
    data_dict = {}
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, symbol in enumerate(selected_symbols):
        status_text.text(f"Loading data: {symbol} ({i+1}/{len(selected_symbols)})")
        df = load_data_from_db(symbol, db_path, start_date, end_date)
        if not df.empty:
            data_dict[symbol] = df
        progress_bar.progress((i + 1) / len(selected_symbols))
    
    if not data_dict:
        st.error("No data loaded for selected symbols")
        return None
    
    status_text.text("Generating signals...")
    
    # Generate signals
    sg = get_signal_generator()
    all_signals = []
    
    for i, (symbol, df) in enumerate(data_dict.items()):
        status_text.text(f"Generating signals: {symbol} ({i+1}/{len(data_dict)})")
        try:
            signals = sg.generate_from_file(df, symbol)
            all_signals.extend(signals)
        except Exception as e:
            st.warning(f"Error generating signals for {symbol}: {e}")
    
    progress_bar.empty()
    status_text.empty()
    
    if not all_signals:
        st.info("No signals generated")
        return None
    
    # Filter and sort signals
    filtered_signals = filter_buy_signals(all_signals, min_signal_strength)
    
    if not filtered_signals:
        st.info("No BUY signals with non-zero strength found")
        return None
    
    filtered_signals = sorted(
        filtered_signals,
        key=lambda s: s.date if s.date is not None else pd.Timestamp.min
    )
    
    # Execute trades
    with st.spinner("Executing trades..."):
        trades_df, summary, portfolio = _execute_all_trades(
            filtered_signals, data_dict, TradeAgent, allocation_params
        )
    
    # Display results
    return summary, trades_df, portfolio, data_dict


def _render_csv_backtest(CSV_FILES, TradeAgent, allocation_params, min_signal_strength: int):
    """Render CSV-based backtest UI."""
    # Checkbox to toggle forced close of open positions at end of data
    try:
        default_force = get_force_close_at_end()
    except Exception:
        default_force = False

    force_close = st.checkbox("Force close open positions at end of data", value=default_force)
    # Persist flag in shared common module
    set_force_close_at_end(bool(force_close))

    # Security selection multiselect (use get_security_name as label)
    try:
        security_labels = []
        file_to_security = {}
        for f in CSV_FILES or []:
            try:
                sec = get_security_name(f)
            except Exception:
                sec = f
            file_to_security.setdefault(sec, []).append(f)
            if sec not in security_labels:
                security_labels.append(sec)
    except Exception:
        security_labels = []
        file_to_security = {}

    selected_secs = st.multiselect("Select securities to backtest", options=security_labels, default=security_labels)
    # Build filtered file list matching selected securities
    filtered_files = []
    for sec in selected_secs:
        filtered_files.extend(file_to_security.get(sec, []))

    if st.button("Run Backtest"):
        with st.spinner("Running backtest..."):
            # pass filtered_files (if none selected, fall back to original CSV_FILES)
            results = _run_backtest(filtered_files or CSV_FILES, TradeAgent, allocation_params, min_signal_strength)
            if results:
                summary, trades_df, portfolio, data_dict = results
                st.session_state['backtest_results'] = {
                    'summary': summary,
                    'trades_df': trades_df,
                    'portfolio': portfolio,
                    'data_dict': data_dict
                }

    # Display last results (persisted across reruns)
    if 'backtest_results' in st.session_state:
        stored = st.session_state.get('backtest_results') or {}
        _display_results(
            stored.get('summary'),
            stored.get('trades_df'),
            stored.get('portfolio'),
            stored.get('data_dict')
        )


def _run_backtest(CSV_FILES: List[str], TradeAgent, allocation_params: dict, min_signal_strength: int) -> Optional[Tuple[Any, pd.DataFrame, Any, dict]]:
    """Execute the backtest logic."""
    if not CSV_FILES:
        st.error("No CSV files provided.")
        return None

    # Use singleton SignalGenerator
    sg = get_signal_generator()

    # Process files and generate signals
    results = _process_files_parallel(CSV_FILES, sg)

    if not results:
        st.error("No valid data was loaded.")
        return None

    # Combine results
    all_signals = []
    file_dataframes = {}

    for file_name, df, signals in results:
        file_dataframes[file_name] = df
        all_signals.extend(signals)

    if not all_signals:
        st.info("No signals were generated.")
        return None

    # Filter signals - only BUY signals with non-zero strength
    filtered_signals = filter_buy_signals(all_signals, min_signal_strength)

    if not filtered_signals:
        st.info("No BUY signals with non-zero strength found.")
        return None

    # Sort signals by date (chronological order across all securities)
    filtered_signals = sorted(
        filtered_signals,
        key=lambda s: s.date if s.date is not None else pd.Timestamp.min
    )

    # Execute all trades with a single TradeAgent
    trades_df, summary, portfolio = _execute_all_trades(
        filtered_signals, file_dataframes, TradeAgent, allocation_params
    )

    # Return results for persisted display
    return summary, trades_df, portfolio, file_dataframes


def _process_files_parallel(
        csv_files: List[str],
        sg
) -> List[Tuple[str, pd.DataFrame, List[Signal]]]:
    """Process CSV files in parallel for better performance.

    New behavior:
    - Load each CSV file into a DataFrame
    - Group files by security name extracted from filename
    - Sort each group's files by start date and concatenate into a single DataFrame per security
    - Run the provided SignalGenerator `sg` on each merged DataFrame and return list of (security_name, merged_df, signals)
    """
    # First load all dataframes (in parallel) into a list of (file_name, df)
    loaded = []
    with ThreadPoolExecutor(max_workers=min(len(csv_files) or 1, 4)) as executor:
        future_to_file = {executor.submit(load_data, file_name, 'backtest_data'): file_name for file_name in csv_files}
        for future in as_completed(future_to_file):
            fname = future_to_file[future]
            try:
                df = future.result()
                if df is None or df.empty:
                    logger = None
                    # Use streamlit warning if available
                    try:
                        st.warning(f"No data in file: {fname}")
                    except Exception:
                        pass
                    continue
                loaded.append((fname, df))
            except Exception as e:
                try:
                    st.warning(f"Failed to load {fname}: {e}")
                except Exception:
                    pass

    # Helper to extract security name
    def _extract_security(fname: str) -> str:
        try:
            parts = fname.split("-")
            if len(parts) >= 8:
                return parts[7]
        except Exception:
            pass
        return fname.rsplit('.', 1)[0] if isinstance(fname, str) else str(fname)

    # Group by security and sort each group's dfs by start date
    grouped: dict = {}
    for fname, df in loaded:
        sec = _extract_security(fname)
        start = pd.to_datetime(df.index.min()) if hasattr(df, 'index') and len(df.index) > 0 else pd.NaT
        grouped.setdefault(sec, []).append((fname, df, start))

    merged_results: List[Tuple[str, pd.DataFrame, List[Signal]]] = []
    for sec in sorted(grouped.keys()):
        entries = grouped[sec]
        entries.sort(key=lambda x: (pd.NaT if pd.isna(x[2]) else x[2]))
        # Concatenate the dataframes for this security, in chronological order
        dfs = [e[1] for e in entries]
        try:
            merged_df = pd.concat(dfs).sort_index()
            # drop duplicate indices keeping first occurrence
            merged_df = merged_df[~merged_df.index.duplicated(keep='first')]
        except Exception:
            # fallback: take first df
            merged_df = dfs[0]

        # Run signal generator on merged dataframe
        try:
            signals = sg.generate_from_file(merged_df, sec) or []
        except Exception as e:
            try:
                st.warning(f"Signal generation failed for {sec}: {e}")
            except Exception:
                pass
            signals = []

        merged_results.append((sec, merged_df, signals))

    return merged_results


def _process_single_file(
        file_name: str,
        sg
) -> Optional[Tuple[str, pd.DataFrame, List[Signal]]]:
    """Process a single CSV file and generate signals."""
    import traceback
    try:
        df = load_data(file_name, "backtest_data")
        if df is None or df.empty:
            return None  # type: ignore[return-value]

        signals = sg.generate_from_file(df, file_name) or []
        return file_name, df, signals
    except Exception as e:
        # Include traceback for debugging
        tb = traceback.format_exc()
        raise Exception(f"Error processing {file_name}: {e}\nTraceback:\n{tb}")


def _execute_all_trades(
        signals: List[Signal],
        file_dataframes: dict,
        TradeAgent,
        allocation_params: dict
) -> Tuple[pd.DataFrame, dict, Any]:
    """Execute all trades chronologically with portfolio tracking."""
    # Create a single TradeAgent
    ta = TradeAgent(**allocation_params)

    # Initialize state
    ta._reset_state()

    # Store DataFrame mapping for position exit processing
    ta._df_mapping = file_dataframes

    # Apply agent-level signal prioritization rules (e.g., 3:20 PM same-day tie-breakers)
    try:
        if hasattr(ta, 'prepare_signals_for_execution'):
            signals = ta.prepare_signals_for_execution(signals)
    except Exception:
        pass

    # Process each signal in chronological order
    for signal in signals:
        # Find the matching DataFrame for this signal's security
        matching_df = _find_matching_dataframe(signal.symbol, file_dataframes)

        if matching_df is None:
            continue

        # Process any pending exits that occur before this signal's date
        ta._process_pending_exits(signal.date)

        # Execute the trade
        trade = ta._execute_single_trade(matching_df, signal)
        if trade:
            ta.trades.append(trade)

    # Process any remaining pending exits (for positions that close after last signal)
    # Use a far future date to ensure all exits are processed
    # Get timezone from data if available to avoid comparison errors
    try:
        sample_df = next(iter(file_dataframes.values()))
        if hasattr(sample_df.index, 'tz') and sample_df.index.tz is not None:
            max_timestamp = pd.Timestamp.max.tz_localize(sample_df.index.tz)
        else:
            max_timestamp = pd.Timestamp.max
    except:
        max_timestamp = pd.Timestamp.max
    
    ta._process_pending_exits(max_timestamp)

    # If force-close is enabled, force-close any remaining open positions using per-security dataframes
    try:
        if get_force_close_at_end():
            ta.force_close_open_positions(file_dataframes)
            # finalize forced closes
            ta._process_pending_exits(max_timestamp)
    except Exception:
        pass

    # Calculate final results
    ta.final_balance = ta.cash + ta.portfolio.total_capital_used
    ta.final_pnl = ta.final_balance - ta.initial_capital

    # Convert trades to DataFrame
    trades_df = ta._trades_to_dataframe()

    # Get summary
    summary = ta.get_summary()

    # Get portfolio for display
    portfolio = ta.get_portfolio()

    return trades_df, summary, portfolio


def _find_matching_dataframe(security: str, file_dataframes: dict) -> Optional[pd.DataFrame]:
    """Find the DataFrame that matches the given security name."""
    if not security:
        return None  # type: ignore[return-value]

    for file_name, df in file_dataframes.items():
        # Try to extract security name from file
        try:
            parts = file_name.split("-")
            # Handle different file naming patterns
            # Pattern: DD-MM-YYYY-TO-DD-MM-YYYY-SECURITY-...
            if len(parts) >= 8:
                file_security = parts[7]
                if file_security == security:
                    return df
            # Fallback: check if security name appears anywhere in filename
            elif security in file_name:
                return df
        except (IndexError, AttributeError):
            continue

    return None  # type: ignore[return-value]


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


def _get_df_for_trade(security: str, data_dict: dict) -> Optional[pd.DataFrame]:
    if not security or not data_dict:
        return None
    if security in data_dict:
        return data_dict[security]
    for key, df in data_dict.items():
        try:
            if security in str(key):
                return df
        except Exception:
            continue
    return None


def _display_results(summary, trades_df: pd.DataFrame, portfolio=None, data_dict: Optional[dict] = None):
    """Display backtest results in Streamlit."""
    if summary is not None:
        st.subheader("Backtest Summary")
        # Convert TradeSummary to dict for display
        if hasattr(summary, 'to_dict'):
            summary_dict = summary.to_dict()
        else:
            summary_dict = summary
        st.table(summary_dict)

    if trades_df is not None and not trades_df.empty:
        st.subheader(f"Completed Trades ({len(trades_df)} total)")

        # Format dates for display
        display_df = _format_trades_for_display(trades_df)
        st.dataframe(display_df, use_container_width=True)

        # Show summary statistics
        _show_trade_statistics(trades_df)

        if data_dict:
            st.subheader("Trade Visualizations")
            show_trade_charts = st.checkbox("Show trade visualizations", value=False, key="bt_show_trade_viz")
            if show_trade_charts:
                bars_padding = st.slider(
                    "Bars before/after trade",
                    min_value=10,
                    max_value=250,
                    value=60,
                    step=10,
                    key="bt_bars_padding"
                )
                max_trades = st.number_input(
                    "Max trades to render",
                    min_value=1,
                    max_value=100,
                    value=20,
                    step=1,
                    key="bt_max_trades"
                )

                strat_cache: dict = {}
                atr_cache: dict = {}
                for sec_key, df in data_dict.items():
                    try:
                        if df is None or df.empty:
                            continue
                        fvg = FVGOrderBlocks()
                        fvg.run(df)
                        sonar = SonarlaplaceOrderBlocks()
                        sonar.run(df)
                        strat_cache[sec_key] = (fvg, sonar)
                        atr_cache[sec_key] = atr_series(df, period=14)
                    except Exception:
                        continue

                trades_to_render = trades_df.head(int(max_trades))
                for trade_num, (_, trade_row) in enumerate(trades_to_render.iterrows(), start=1):
                    security = trade_row.get('security')
                    df = _get_df_for_trade(security, data_dict)
                    if df is None or df.empty:
                        continue

                    entry_idx = None
                    if 'entry_index' in trade_row and pd.notna(trade_row['entry_index']):
                        try:
                            entry_idx = int(trade_row['entry_index'])
                        except Exception:
                            entry_idx = None
                    if entry_idx is None:
                        entry_idx = _index_from_date(df, trade_row.get('entry_date'))

                    exit_idx = _index_from_date(df, trade_row.get('exit_date'))

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

                    total_rows = len(df)
                    start_idx = max(0, min(trade_start, trade_end) - bars_padding)
                    end_idx = min(total_rows - 1, max(trade_start, trade_end) + bars_padding)
                    df_slice = df.iloc[start_idx:end_idx + 1]

                    entry_local = entry_idx - start_idx if entry_idx is not None else None
                    exit_local = exit_idx - start_idx if exit_idx is not None else None

                    signals = _build_trade_signals(entry_local, exit_local, entry_price, exit_price, trade_side)

                    fvg_boxes = []
                    sonar_boxes = []
                    for key, (fvg, sonar) in strat_cache.items():
                        try:
                            if security == key or security in str(key):
                                fvg_boxes = _subset_boxes(
                                    (fvg.bull_boxes or []) + (fvg.bear_boxes or []),
                                    start_idx,
                                    end_idx
                                )
                                sonar_boxes = _subset_boxes(
                                    (sonar.long_boxes or []) + (sonar.short_boxes or []),
                                    start_idx,
                                    end_idx
                                )
                                break
                        except Exception:
                            continue

                    with st.expander(f"Trade {trade_num} ({security})"):
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

                        atr_full = atr_cache.get(security)
                        if atr_full is None:
                            atr_full = next(iter(atr_cache.values()), None)
                        if atr_full is not None:
                            atr_slice = atr_full.iloc[start_idx:end_idx + 1]
                            ax_atr.plot([mdates.date2num(d) for d in df_slice.index], atr_slice.values, color='#6a51a3', linewidth=1.2)
                        ax_atr.set_ylabel("ATR(14)")
                        ax_atr.grid(True, linestyle='--', linewidth=0.5, alpha=0.4)

                        st.pyplot(fig)

    # Display open positions (portfolio)
    if portfolio is not None:
        _display_portfolio(portfolio)


def _format_trades_for_display(trades_df: pd.DataFrame) -> pd.DataFrame:
    """Format trades DataFrame for display."""
    # Format date columns
    df = format_trades_dates(trades_df)

    # Format numeric columns
    numeric_formats = {
        'entry_price': '{:.2f}',
        'exit_price': '{:.2f}',
        'pnl': '{:.2f}',
        'cash_before': '{:.2f}',
        'cash_after': '{:.2f}',
        'money_allocated': '{:.2f}'
    }
    df = format_numeric_columns(df, numeric_formats)

    # Format lockin_period
    if 'lockin_period' in df.columns:
        df['lockin_period'] = df['lockin_period'].apply(
            lambda x: str(x) if pd.notna(x) else ''
        )

    return df


def _show_trade_statistics(trades_df: pd.DataFrame):
    """Show additional trade statistics in rupees."""
    if 'pnl' not in trades_df.columns:
        return

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        total_pnl = trades_df['pnl'].sum()
        st.metric("Total P&L", f"₹{total_pnl:,.2f}")

    with col2:
        avg_pnl = trades_df['pnl'].mean()
        st.metric("Avg P&L per Trade", f"₹{avg_pnl:,.2f}")

    with col3:
        if 'money_allocated' in trades_df.columns:
            total_allocated = trades_df['money_allocated'].sum()
            roi = (total_pnl / total_allocated * 100) if total_allocated > 0 else 0
            st.metric("ROI", f"{roi:.2f}%")

    with col4:
        if 'lockin_period' in trades_df.columns:
            # Calculate average holding period in days
            periods = trades_df['lockin_period'].dropna()
            if len(periods) > 0:
                avg_days = sum(p.days for p in periods if hasattr(p, 'days')) / len(periods)
                st.metric("Avg Holding", f"{avg_days:.1f} days")


def _display_portfolio(portfolio):
    """Display open positions in the portfolio."""
    st.subheader("Open Positions (Portfolio)")

    # Try to obtain positions list
    try:
        positions = portfolio.get_all_positions()
    except Exception:
        positions = []

    if not positions:
        st.info("No open positions remaining.")
        return

    # Show portfolio summary
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Open Positions", len(positions))

    with col2:
        total_cap_used = getattr(portfolio, 'total_capital_used', None)
        if total_cap_used is None:
            # try summing from positions if available
            try:
                total_cap_used = sum(getattr(p, 'money_allocated', 0) for p in positions)
            except Exception:
                total_cap_used = 0.0
        st.metric("Capital in Positions", f"₹{total_cap_used:,.2f}")

    with col3:
        try:
            total_value = sum(getattr(p, 'current_value', getattr(p, 'shares', 0) * getattr(p, 'entry_price', 0)) for p in positions)
        except Exception:
            total_value = 0.0
        st.metric("Current Value", f"₹{total_value:,.2f}")

    # Prepare positions table
    try:
        portfolio_df = portfolio.to_dataframe()
    except Exception:
        # fallback to building a DataFrame from positions
        rows = []
        for p in positions:
            rows.append({
                'security': getattr(p, 'security', getattr(p, 'symbol', '')),
                'entry_date': getattr(p, 'entry_date', ''),
                'entry_price': getattr(p, 'entry_price', ''),
                'shares': getattr(p, 'shares', ''),
                'money_allocated': getattr(p, 'money_allocated', ''),
                'stop_loss': getattr(p, 'stop_loss', ''),
                'target': getattr(p, 'target', ''),
                'current_value': getattr(p, 'current_value', getattr(p, 'shares', 0) * getattr(p, 'entry_price', 0))
            })
        portfolio_df = pd.DataFrame(rows)

    if portfolio_df is None or portfolio_df.empty:
        st.info("No portfolio rows to display.")
        return

    display_df = portfolio_df.copy()
    # Format date column if present
    if 'entry_date' in display_df.columns:
        display_df['entry_date'] = pd.to_datetime(display_df['entry_date'], errors='coerce').dt.strftime('%Y-%m-%d')

    # Format numeric columns
    numeric_cols = ['entry_price', 'money_allocated', 'stop_loss', 'target', 'current_value']
    for col in numeric_cols:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: f"{x:,.2f}" if pd.notna(x) else '')

    st.dataframe(display_df, use_container_width=True)
