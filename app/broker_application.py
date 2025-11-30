import logging
import os
from typing import List, Optional

from app.agent.signal_generator import get_signal_generator
from app.service.broker_service import BrokerConfig
from app.utility.file_util import read_csv_into_df

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# locate backtest data directory relative to project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
BACKTEST_DATA_DIR = os.path.join(PROJECT_ROOT, 'resource', 'backtest_data')
BACKTEST_CSV_FILES: List[str] = [f for f in os.listdir(BACKTEST_DATA_DIR) if f.endswith('.csv')] if os.path.isdir(BACKTEST_DATA_DIR) else []




def run_executor_on_backtest_files(
    broker_config: Optional[BrokerConfig] = None,
    dry_run: bool = True,
    file_filter: Optional[str] = None,
) -> None:
    """Run SignalGenerator for CSVs in the backtest directory and execute trades.

    Args:
        broker_config: BrokerConfig if live execution is desired. If None and dry_run False, BrokerService will not be used.
        dry_run: if True, no real orders will be sent to broker.
        file_filter: optional substring to filter CSV filenames.
    """
    sg = get_signal_generator()

    # Determine candidate files
    csv_files = BACKTEST_CSV_FILES
    if file_filter:
        csv_files = [f for f in csv_files if file_filter in f]

    if not csv_files:
        logger.warning("No backtest CSV files found in %s", BACKTEST_DATA_DIR)
        return

    executor = TradeAgentExecutor(broker_config=broker_config, dry_run=dry_run)

    for fname in csv_files:
        full_path = os.path.join(BACKTEST_DATA_DIR, fname)
        logger.info("Processing file %s", full_path)
        try:
            df = read_csv_into_df(full_path)
            enhanced = sg.generate_from_file(df, fname)
            trades_df = executor.execute_and_place(df, enhanced)
            logger.info("Finished: %s produced %d trades", fname, len(executor.trades))
        except Exception:
            logger.exception("Failed processing %s", full_path)


if __name__ == '__main__':
    # Simple CLI: run in dry-run mode by default
    import argparse

    parser = argparse.ArgumentParser(description='Run backtest signal generation and (optionally) execute trades via broker')
    parser.add_argument('--live', action='store_true', help='If set, attempt to place live orders using BrokerService (requires BrokerConfig in code)')
    parser.add_argument('--filter', type=str, default=None, help='Filter to select CSV file(s) containing this substring')
    args = parser.parse_args()

    # If you want to run live, construct BrokerConfig here or fetch from env/config
    broker_cfg = None
    if args.live:
        # Example: populate these from environment variables or secure config
        broker_cfg = BrokerConfig(api_key=os.environ.get('KITE_API_KEY', ''), access_token=os.environ.get('KITE_ACCESS_TOKEN', ''))
        if not broker_cfg.api_key or not broker_cfg.access_token:
            logger.warning('Live mode requested but KITE_API_KEY or KITE_ACCESS_TOKEN not provided in environment; running dry-run instead')
            broker_cfg = None

    run_executor_on_backtest_files(broker_config=broker_cfg, dry_run=(broker_cfg is None), file_filter=args.filter)
