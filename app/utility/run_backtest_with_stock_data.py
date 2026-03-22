"""
Run backtest optimizer using stock_data.db

This script loads data from the stock_data table and runs backtest optimization
with different risk-reward ratios and parameters.
"""
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# Add app directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.optimizer import BacktestOptimizer
from agent.paper_trade_agent import PaperTradeAgent
from agent.signal_generator import SignalGenerator
from strategy.fvgorderblocks import FVGOrderBlocks

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


def load_stock_data_from_db(db_path: str = 'resource/stock_data.db', max_symbols: int = None):
    """
    Load OHLCV data from stock_data table.
    
    Args:
        db_path: Path to database file
        max_symbols: Maximum number of symbols to load (for testing)
    
    Returns:
        Dictionary mapping symbol to DataFrame
    """
    logger.info("="*80)
    logger.info("Loading Data from Database")
    logger.info("="*80)
    
    conn = sqlite3.connect(db_path)
    
    # Get list of symbols with sufficient data
    query = """
        SELECT symbol, COUNT(*) as count
        FROM stock_data
        GROUP BY symbol
        HAVING count >= 100
        ORDER BY symbol
    """
    symbols_df = pd.read_sql_query(query, conn)
    symbols = symbols_df['symbol'].tolist()
    
    if max_symbols:
        symbols = symbols[:max_symbols]
    
    logger.info(f"Loading data for {len(symbols)} symbols...")
    
    data_dict = {}
    for i, symbol in enumerate(symbols):
        query = """
            SELECT datetime, open, high, low, close, volume
            FROM stock_data
            WHERE symbol = ?
            ORDER BY datetime
        """
        df = pd.read_sql_query(query, conn, params=[symbol])
        
        if not df.empty:
            # Convert datetime to pandas datetime and set as index
            df['datetime'] = pd.to_datetime(df['datetime'])
            df.set_index('datetime', inplace=True)
            
            # Rename columns to match expected format (capitalize first letter)
            df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            
            data_dict[symbol] = df
            
            if (i + 1) % 20 == 0:
                logger.info(f"Loaded {i + 1}/{len(symbols)} symbols")
    
    conn.close()
    
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
    logger.info("="*80)
    logger.info("Running Backtest Optimization")
    logger.info("="*80)
    
    # Default parameter ranges with focus on risk-reward ratios
    # Risk (stop loss): 3%, 4%, 5%
    # Reward (target): 9%, 12%, 15%
    # Risk-reward ratios calculated: 9/3=3.0, 12/3=4.0, 15/3=5.0, 9/4=2.25, 12/4=3.0, 15/4=3.75, 9/5=1.8, 12/5=2.4, 15/5=3.0
    if param_ranges is None:
        param_ranges = {
            'risk_reward_ratio': [1.8, 2.25, 2.4, 3.0, 3.75, 4.0, 5.0],
            'stop_loss_pct': [0.03, 0.04, 0.05],
            'allocation_step': [0.15, 0.2, 0.25],
            'initial_capital': [100000.0]
        }
    
    logger.info(f"Parameter ranges:")
    for key, values in param_ranges.items():
        logger.info(f"  {key}: {values}")
    
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
    total_combinations = len(param_ranges['risk_reward_ratio']) * len(param_ranges['stop_loss_pct']) * len(param_ranges['allocation_step'])
    logger.info("Starting optimization (this may take several minutes)...")
    logger.info(f"Total combinations to test: {total_combinations}")
    
    results_df = optimizer.optimize(
        param_ranges=param_ranges,
        metric='total_pnl',
        max_workers=1  # Use 1 for sequential processing
    )
    
    return results_df


def display_results(results_df: pd.DataFrame, top_n: int = 10):
    """
    Display optimization results.
    
    Args:
        results_df: DataFrame with optimization results
        top_n: Number of top results to display
    """
    logger.info("="*80)
    logger.info("Optimization Results")
    logger.info("="*80)
    
    print("\n" + "="*100)
    print(f"TOP {top_n} PARAMETER COMBINATIONS BY TOTAL P&L")
    print("="*100)
    
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
    
    # Format for better readability
    pd.options.display.float_format = '{:.2f}'.format
    print(top_results.to_string(index=False))
    
    print("\n" + "="*100)
    print("BEST PARAMETERS")
    print("="*100)
    
    best = results_df.iloc[0]
    print(f"\nRisk-Reward Ratio:   {best.get('risk_reward_ratio', 'N/A'):.2f}")
    print(f"Stop Loss %:         {best.get('stop_loss_pct', 'N/A'):.2%}")
    print(f"Allocation Step:     {best.get('allocation_step', 'N/A'):.2f}")
    print(f"\nPerformance Metrics:")
    print(f"  Total P&L:           ₹{best.get('total_pnl', 0):,.2f}")
    print(f"  Total Return:        {best.get('total_return_pct', 0):.2f}%")
    print(f"  Win Rate:            {best.get('win_rate', 0):.2f}%")
    print(f"  Profit Factor:       {best.get('profit_factor', 0):.2f}")
    print(f"  Total Trades:        {best.get('total_trades', 0):.0f}")
    print(f"  Winning Trades:      {best.get('winning_trades', 0):.0f}")
    print(f"  Losing Trades:       {best.get('losing_trades', 0):.0f}")
    print(f"  Max Drawdown:        {best.get('max_drawdown_pct', 0):.2f}%")
    print(f"  Sharpe Ratio:        {best.get('sharpe_ratio', 0):.2f}")
    print(f"  Avg Win:             ₹{best.get('avg_win', 0):,.2f}")
    print(f"  Avg Loss:            ₹{best.get('avg_loss', 0):,.2f}")
    print("="*100)
    
    # Save results to CSV
    output_file = f"optimization_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    results_df.to_csv(output_file, index=False)
    logger.info(f"\nFull results saved to: {output_file}")


def main():
    """Main execution function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run backtest optimization using stock_data.db')
    parser.add_argument('--max-symbols', type=int, default=None, help='Maximum number of symbols to test')
    parser.add_argument('--db-path', type=str, default='resource/stock_data.db', help='Database file path')
    
    args = parser.parse_args()
    
    try:
        logger.info("Starting Backtest Optimization")
        logger.info(f"Database: {args.db_path}")
        
        # Load data from database
        data_dict = load_stock_data_from_db(
            db_path=args.db_path,
            max_symbols=args.max_symbols
        )
        
        if not data_dict:
            raise RuntimeError("No data available for backtesting")
        
        logger.info(f"Data loaded for {len(data_dict)} stocks")
        logger.info(f"Date range: {min(df.index.min() for df in data_dict.values())} to {max(df.index.max() for df in data_dict.values())}")
        
        # Run optimization
        results_df = run_optimization(data_dict)
        
        # Display results
        display_results(results_df)
        
        logger.info("\nBacktest optimization completed successfully!")
        
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
