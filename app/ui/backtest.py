"""
Backtest UI component for running strategy backtests.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple

import pandas as pd
import streamlit as st

from app.model.signal import Signal
from app.utility.utility import load_data
from app.agent.signal_generator import get_signal_generator
from app.ui.signal_utils import filter_buy_signals, format_trades_dates, format_numeric_columns


def render_backtest(CSV_FILES, SignalGenerator, TradeAgent, allocation_params):
    """Render the backtest UI and execute backtests."""
    if st.button("Run Backtest"):
        with st.spinner("Running backtest..."):
            _run_backtest(CSV_FILES, TradeAgent, allocation_params)


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
    """Process CSV files in parallel for better performance."""
    results = []

    # Use ThreadPoolExecutor for I/O-bound operations
    with ThreadPoolExecutor(max_workers=min(len(csv_files), 4)) as executor:
        future_to_file = {
            executor.submit(_process_single_file, file_name, sg): file_name
            for file_name in csv_files
        }

        for future in as_completed(future_to_file):
            file_name = future_to_file[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                st.warning(f"Failed to process {file_name}: {e}")

    return results


def _process_single_file(
    file_name: str,
    sg
) -> Tuple[str, pd.DataFrame, List[Signal]]:
    """Process a single CSV file and generate signals."""
    import traceback
    try:
        df = load_data(file_name)
        if df is None or df.empty:
            return None

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
) -> Tuple[pd.DataFrame, dict]:
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
    ta._process_pending_exits(pd.Timestamp.max)

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


def _find_matching_dataframe(security: str, file_dataframes: dict) -> pd.DataFrame:
    """Find the DataFrame that matches the given security name."""
    if not security:
        return None

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

    return None


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

    positions = portfolio.get_all_positions()

    if not positions:
        st.info("No open positions remaining.")
        return

    # Show portfolio summary
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Open Positions", len(positions))

    with col2:
        st.metric("Capital in Positions", f"₹{portfolio.total_capital_used:,.2f}")

    with col3:
        total_value = sum(pos.current_value for pos in positions)
        st.metric("Current Value", f"₹{total_value:,.2f}")

    # Show positions table
    portfolio_df = portfolio.to_dataframe()
    if not portfolio_df.empty:
        # Format for display
        display_df = portfolio_df.copy()

        # Format date column
        if 'entry_date' in display_df.columns:
            display_df['entry_date'] = pd.to_datetime(
                display_df['entry_date'], errors='coerce'
            ).dt.strftime('%Y-%m-%d')

        # Format numeric columns
        numeric_cols = ['entry_price', 'money_allocated', 'stop_loss', 'target', 'current_value']
        for col in numeric_cols:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(
                    lambda x: f"{x:,.2f}" if pd.notna(x) else ''
                )

        st.dataframe(display_df, use_container_width=True)