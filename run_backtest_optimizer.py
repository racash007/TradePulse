"""
Backtest Optimizer Runner - Download data and run optimized backtests.

This script:
1. Downloads NSE F&O stock list using Angel One API
2. Downloads 5 years of OHLCV data for each stock
3. Stores data in SQLite database
4. Runs backtests with different parameter combinations
5. Reports optimal parameters and maximum profit
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'app'))

from service.angel_data_downloader import AngelDataDownloader
from service.database_manager import DatabaseManager
from ui.optimizer import BacktestOptimizer
from agent.paper_trade_agent import PaperTradeAgent
from agent.signal_generator import SignalGenerator
from strategy.fvgorderblocks import FVGOrderBlocks
from utility.env_loader import load_env

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('backtest_optimizer.log')
    ]
)
logger = logging.getLogger(__name__)


def load_credentials():
    """Load Angel One API credentials from environment."""
    try:
        # Try to load from .env file
        load_env()
    except:
        pass
    
    credentials = {
        'api_key': os.getenv('ANGEL_API_KEY'),
        'client_id': os.getenv('ANGEL_CLIENT_ID'),
        'password': os.getenv('ANGEL_PASSWORD'),
        'totp_secret': os.getenv('ANGEL_TOTP_SECRET')
    }
    
    # Validate credentials
    missing = [k for k, v in credentials.items() if not v]
    if missing:
        raise ValueError(f"Missing credentials: {', '.join(missing)}. Please set in .env file.")
    
    return credentials


def download_data(db_manager: DatabaseManager, years: int = 5, force_refresh: bool = False):
    """
    Download NSE F&O stock data.
    
    Args:
        db_manager: Database manager instance
        years: Number of years of historical data
        force_refresh: If True, re-download even if data exists
    """
    logger.info("=" * 80)
    logger.info("STEP 1: Downloading NSE F&O Stock Data")
    logger.info("=" * 80)
    
    # Check if we already have data
    existing_symbols = db_manager.get_symbols_with_data(min_records=100)
    if existing_symbols and not force_refresh:
        logger.info(f"Found existing data for {len(existing_symbols)} symbols")
        user_input = input("Do you want to use existing data? (y/n): ").strip().lower()
        if user_input == 'y':
            logger.info("Using existing data from database")
            return existing_symbols
    
    # Load credentials
    logger.info("Loading Angel One API credentials...")
    credentials = load_credentials()
    
    # Initialize downloader
    downloader = AngelDataDownloader(**credentials)
    
    # Connect to API
    logger.info("Connecting to Angel One API...")
    if not downloader.connect():
        raise RuntimeError("Failed to connect to Angel One API")
    
    try:
        # Get F&O stocks list
        logger.info("Fetching NSE F&O stocks list...")
        fno_stocks = downloader.get_nse_fno_stocks()
        
        if not fno_stocks:
            raise RuntimeError("No F&O stocks found")
        
        logger.info(f"Found {len(fno_stocks)} F&O stocks")
        
        # Save stocks to database
        db_manager.save_stocks(fno_stocks)
        
        # Download historical data
        logger.info(f"Downloading {years} years of historical data...")
        data_dict = downloader.download_bulk_historical_data(
            symbols=fno_stocks,
            years=years,
            interval="ONE_DAY"
        )
        
        # Save data to database
        logger.info("Saving data to database...")
        for symbol, df in data_dict.items():
            db_manager.save_ohlcv_data(symbol, df)
        
        logger.info(f"Successfully downloaded and saved data for {len(data_dict)} symbols")
        
        return list(data_dict.keys())
        
    finally:
        downloader.close()


def load_data_from_db(db_manager: DatabaseManager, symbols: list = None, max_symbols: int = None):
    """
    Load OHLCV data from database.
    
    Args:
        db_manager: Database manager instance
        symbols: List of symbols to load (if None, load all)
        max_symbols: Maximum number of symbols to load
    
    Returns:
        Dictionary mapping symbol to DataFrame
    """
    logger.info("=" * 80)
    logger.info("STEP 2: Loading Data from Database")
    logger.info("=" * 80)
    
    if symbols is None:
        symbols = db_manager.get_symbols_with_data(min_records=100)
    
    if max_symbols:
        symbols = symbols[:max_symbols]
    
    logger.info(f"Loading data for {len(symbols)} symbols...")
    
    data_dict = {}
    for i, symbol in enumerate(symbols):
        df = db_manager.get_ohlcv_data(symbol)
        if df is not None and not df.empty:
            data_dict[symbol] = df
            if (i + 1) % 10 == 0:
                logger.info(f"Loaded {i + 1}/{len(symbols)} symbols")
    
    logger.info(f"Successfully loaded data for {len(data_dict)} symbols")
    return data_dict


def run_optimization(data_dict: dict, param_ranges: dict = None):
    """
    Run backtest optimization.
    
    Args:
        data_dict: Dictionary mapping symbol to DataFrame
        param_ranges: Parameter ranges to test
    
    Returns:
        DataFrame with optimization results
    """
    logger.info("=" * 80)
    logger.info("STEP 3: Running Backtest Optimization")
    logger.info("=" * 80)
    
    # Default parameter ranges
    if param_ranges is None:
        param_ranges = {
            'risk_reward_ratio': [1.5, 2.0, 2.5, 3.0],
            'stop_loss_pct': [0.02, 0.03, 0.04, 0.05],
            'allocation_step': [0.15, 0.2, 0.25],
            'initial_capital': [100000.0]
        }
    
    logger.info(f"Parameter ranges: {param_ranges}")
    
    # Initialize components
    signal_generator = SignalGenerator()
    
    # Create optimizer
    optimizer = BacktestOptimizer(
        data_dict=data_dict,
        strategy_class=FVGOrderBlocks,
        trade_agent_class=PaperTradeAgent,
        signal_generator=signal_generator
    )
    
    # Run optimization
    logger.info("Starting optimization (this may take a while)...")
    results_df = optimizer.optimize(
        param_ranges=param_ranges,
        metric='total_pnl',
        max_workers=1  # Use 1 for sequential, increase for parallel
    )
    
    return results_df


def display_results(results_df: pd.DataFrame, top_n: int = 10):
    """
    Display optimization results.
    
    Args:
        results_df: DataFrame with optimization results
        top_n: Number of top results to display
    """
    logger.info("=" * 80)
    logger.info("STEP 4: Optimization Results")
    logger.info("=" * 80)
    
    print("\n" + "=" * 100)
    print(f"TOP {top_n} PARAMETER COMBINATIONS BY TOTAL P&L")
    print("=" * 100)
    
    # Select columns to display
    display_cols = [
        'risk_reward_ratio', 'stop_loss_pct', 'allocation_step',
        'total_pnl', 'total_return_pct', 'win_rate', 'profit_factor',
        'total_trades', 'max_drawdown_pct', 'sharpe_ratio'
    ]
    
    # Filter columns that exist
    display_cols = [col for col in display_cols if col in results_df.columns]
    
    # Display top results
    top_results = results_df.head(top_n)[display_cols]
    print(top_results.to_string(index=False))
    
    print("\n" + "=" * 100)
    print("BEST PARAMETERS")
    print("=" * 100)
    
    best = results_df.iloc[0]
    print(f"Risk-Reward Ratio:   {best.get('risk_reward_ratio', 'N/A'):.2f}")
    print(f"Stop Loss %:         {best.get('stop_loss_pct', 'N/A'):.2%}")
    print(f"Allocation Step:     {best.get('allocation_step', 'N/A'):.2f}")
    print(f"\nTotal P&L:           ₹{best.get('total_pnl', 0):,.2f}")
    print(f"Total Return:        {best.get('total_return_pct', 0):.2f}%")
    print(f"Win Rate:            {best.get('win_rate', 0):.2f}%")
    print(f"Profit Factor:       {best.get('profit_factor', 0):.2f}")
    print(f"Total Trades:        {best.get('total_trades', 0):.0f}")
    print(f"Max Drawdown:        {best.get('max_drawdown_pct', 0):.2f}%")
    print(f"Sharpe Ratio:        {best.get('sharpe_ratio', 0):.2f}")
    print("=" * 100)
    
    # Save results to CSV
    output_file = f"optimization_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    results_df.to_csv(output_file, index=False)
    logger.info(f"Results saved to: {output_file}")


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description='Run backtest optimization with Angel One data')
    parser.add_argument('--years', type=int, default=5, help='Years of historical data')
    parser.add_argument('--max-symbols', type=int, default=None, help='Maximum number of symbols to test')
    parser.add_argument('--db-path', type=str, default='market_data.db', help='Database file path')
    parser.add_argument('--force-refresh', action='store_true', help='Force re-download of data')
    parser.add_argument('--skip-download', action='store_true', help='Skip data download step')
    
    args = parser.parse_args()
    
    try:
        logger.info("Starting Backtest Optimization Pipeline")
        logger.info(f"Database: {args.db_path}")
        logger.info(f"Historical data: {args.years} years")
        
        # Initialize database
        db_manager = DatabaseManager(db_path=args.db_path)
        
        # Step 1: Download data (or skip)
        if not args.skip_download:
            symbols = download_data(
                db_manager=db_manager,
                years=args.years,
                force_refresh=args.force_refresh
            )
        else:
            logger.info("Skipping data download (--skip-download flag)")
            symbols = None
        
        # Step 2: Load data from database
        data_dict = load_data_from_db(
            db_manager=db_manager,
            symbols=symbols,
            max_symbols=args.max_symbols
        )
        
        if not data_dict:
            raise RuntimeError("No data available for backtesting")
        
        # Step 3: Run optimization
        results_df = run_optimization(data_dict)
        
        # Step 4: Display results
        display_results(results_df)
        
        logger.info("Backtest optimization completed successfully!")
        
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if 'db_manager' in locals():
            db_manager.close()


if __name__ == '__main__':
    main()
