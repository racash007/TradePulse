import logging
import os
from typing import List, Optional
import argparse
import asyncio

import requests
from flask import Flask, jsonify

from agent.signal_generator import get_signal_generator
from agent.trade_agent import TradeAgent
from model import Signal
from service.broker_service import BrokerConfig
from utility.env_loader import load_project_env
from utility.file_util import read_csv_into_df

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# locate backtest data directory relative to project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
BACKTEST_DATA_DIR = os.path.join(PROJECT_ROOT, 'resource', 'backtest_data')
BACKTEST_CSV_FILES: List[str] = [f for f in os.listdir(BACKTEST_DATA_DIR) if f.endswith('.csv')] if os.path.isdir(BACKTEST_DATA_DIR) else []


class TradePulse:
    def __init__(self, args):
        load_project_env(args.env)
        self.broker_cfg = BrokerConfig(
                    api_key=os.environ.get('KITE_API_KEY', ''),
                    api_scret=os.environ.get('KITE_API_SECRET', ''),
                    request_token=os.environ.get('KITE_REQUEST_TOKEN', None),
                    access_token=os.environ.get('KITE_ACCESS_TOKEN', None),
                    redirect_uri=os.environ.get('KITE_REDIRECT_URI', '')
                )
        self.agent = TradeAgent(broker_config=self.broker_cfg)
        self.app = Flask(__name__)
        self.register_routes()

    def register_routes(self):
        @self.route('/status')
        def status():
            return jsonify({'status': 'ok'})

        @self.route('/start')
        async def start():
            await asyncio.sleep(1)
            self.run_executor()

        @self.route('/login')
        async def login():
            request_token = requests.args.get("request_token")

            if not request_token:
                return """
                    <span style="color: red">
                        Error while generating request token.
                    </span>
                    <a href='/'>Try again.<a>"""

            self.broker_cfg.request_token = request_token

    def run(self, **kwargs):
        self.run(**kwargs)

    def run_executor(self) -> None:
        """Run the TradeAgent executor.

        Args:
            broker_config: Optional BrokerConfig for real order placement.
        """
        sg = get_signal_generator()

        # Determine candidate files
        csv_files = BACKTEST_CSV_FILES

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--env', default=None)
    args = parser.parse_args()
    flask_app = TradePulse(args=args)
    flask_run(debug=True)
       