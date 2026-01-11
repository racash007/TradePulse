"""
Backtest UI component for running strategy backtests.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional, Any
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from model.signal import Signal
from utility.utility import load_data
from utility.file_util import get_security_name
from agent.signal_generator import get_signal_generator
from ui.signal_utils import filter_buy_signals, format_trades_dates, format_numeric_columns
from ui.common import set_force_close_at_end, get_force_close_at_end
from ui.optimizer import BacktestOptimizer
from strategy.fvgorderblocks import FVGOrderBlocks


def load_symbols_from_db(db_path='resource/stock_data.db'):
    """Load available symbols from database."""
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


def load_data_from_db(symbol, db_path='resource/stock_data.db', start_date=None, end_date=None):
    """Load OHLCV data for a symbol from database."""
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


def render_backtest(CSV_FILES, TradeAgent, allocation_params):
    """Render the backtest UI and execute backtests."""
    st.subheader("Backtest Configuration")
    
    # Data source selection
    data_source = st.radio("Data Source", ["CSV Files", "Database"], horizontal=True)
    
    if data_source == "Database":
        _render_database_backtest(TradeAgent, allocation_params)
    else:
        _render_csv_backtest(CSV_FILES, TradeAgent, allocation_params)


def _render_database_backtest(TradeAgent, allocation_params):
    """Render database-based backtest UI."""
    db_path = st.text_input("Database Path", value="resource/stock_data.db")
    
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
                _run_database_backtest(selected_symbols, db_path, start_date, end_date, TradeAgent, allocation_params)


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


def _run_database_backtest(selected_symbols, db_path, start_date, end_date, TradeAgent, allocation_params):
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
        return
    
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
        return
    
    # Filter and sort signals
    filtered_signals = filter_buy_signals(all_signals)
    
    if not filtered_signals:
        st.info("No BUY signals with non-zero strength found")
        return
    
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
    _display_results(summary, trades_df, portfolio)


def _render_csv_backtest(CSV_FILES, TradeAgent, allocation_params):
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
            _run_backtest(filtered_files or CSV_FILES, TradeAgent, allocation_params)


def _run_backtest(CSV_FILES: List[str], TradeAgent, allocation_params: dict):
    """Execute the backtest logic."""
    if not CSV_FILES:
        st.error("No CSV files provided.")
        return

    # Use singleton SignalGenerator
    sg = get_signal_generator()

    # Process files and generate signals
    results = _process_files_parallel(CSV_FILES, sg)

    if not results:
        st.error("No valid data was loaded.")
        return

    # Combine results
    all_signals = []
    file_dataframes = {}

    for file_name, df, signals in results:
        file_dataframes[file_name] = df
        all_signals.extend(signals)

    if not all_signals:
        st.info("No signals were generated.")
        return

    # Filter signals - only BUY signals with non-zero strength
    filtered_signals = filter_buy_signals(all_signals)

    if not filtered_signals:
        st.info("No BUY signals with non-zero strength found.")
        return

    # Sort signals by date (chronological order across all securities)
    filtered_signals = sorted(
        filtered_signals,
        key=lambda s: s.date if s.date is not None else pd.Timestamp.min
    )

    # Execute all trades with a single TradeAgent
    trades_df, summary, portfolio = _execute_all_trades(
        filtered_signals, file_dataframes, TradeAgent, allocation_params
    )

    # Display results
    _display_results(summary, trades_df, portfolio)


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


def _display_results(summary, trades_df: pd.DataFrame, portfolio=None):
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
