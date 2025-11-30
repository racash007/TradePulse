from typing import Optional, List
import logging

import pandas as pd

from app.agent.paper_trade_agent import PaperTradeAgent
from app.model import Trade, SignalType
from app.service.broker_service import BrokerService, BrokerConfig

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class TradeAgent(PaperTradeAgent):
    """Subclass of TradeAgent that can place real orders via BrokerService.

    This executor runs the simulation using TradeAgent logic and then (optionally)
    places corresponding orders using BrokerService.

    Notes:
        - The executor supports dry_run mode which will simulate placements but not
          call the broker API.
        - The implementation places two market orders per completed trade:
            1) an entry order (BUY/SELL) for the trade.shares
            2) an exit order (opposite side) for the same shares at exit time.
          In a production-grade integration you would instead create OCO/SL/target
          orders or manage orders in real-time; this simple approach mirrors the
          historical execution recorded by the simulator.
    """

    def __init__(
            self,
            broker_config: Optional[BrokerConfig] = None,
            exchange: str = 'NSE',
            product: str = 'CNC',
            **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.exchange = exchange
        self.product = product
        self.broker_config = broker_config
        self.broker:BrokerService = BrokerService(self.broker_config)
            # If access token already provided in config, BrokerService.connect() will be called during init

    def execute_and_place(self, df: pd.DataFrame, enhanced_signals: List) -> pd.DataFrame:
        """Run signal execution and optionally place orders for the completed trades.

        Args:
            df: OHLC DataFrame used for simulation (index is dates)
            enhanced_signals: list of Signal objects produced by SignalGenerator
            place_on_exit: if True, place both entry and exit orders to mirror the completed trade

        Returns:
            DataFrame of executed trades (same as TradeAgent.execute_signals)
        """
        # Run simulation (this populates self.trades)
        trades_df = super().execute_signals(df, enhanced_signals)

        # If dry_run or no broker configured, only log
        for trade in self.trades:
            try:
                self._place_trade_via_broker(trade)
            except Exception as exc:
                logger.exception("Failed to place trade for %s: %s", getattr(trade, 'security', None), exc)

        return trades_df

    def _place_trade_via_broker(self, trade: Trade, place_on_exit: bool = True) -> None:
        """Place entry (and optional exit) via BrokerService. Safe no-op if dry_run."""
        side = trade.side

        # Determine transaction types for entry and exit
        exit_txn = 'SELL' if side == SignalType.BUY else 'BUY'

        # Place entry order
        try:
            resp_entry = self.broker.place_order(
                tradingsymbol=trade.security,
                exchange=self.exchange,
                transaction_type=side.value(),
                quantity=trade.shares,
                order_type='LIMIT',
                product=self.product,
                price=trade.entry_price,
            )
            logger.info("Placed entry order: security=%s shares=%d side=%s resp=%s", trade.security, trade.shares,
                        side.value(), resp_entry)
        except Exception:
            logger.exception("Broker entry order failed for %s", trade.security)
            raise

        if place_on_exit and trade.exit_price is not None:
            # For simplicity, place a market exit immediately to mirror historical exit
            try:
                resp_exit = self.broker.place_order(
                    tradingsymbol=trade.security,
                    exchange=self.exchange,
                    transaction_type=exit_txn,
                    quantity=trade.shares,
                    order_type='LIMIT',
                    product=self.product,
                    price=trade.exit_price,
                )
                logger.info("Placed exit order: security=%s shares=%d side=%s resp=%s", trade.security, trade.shares,
                            exit_txn, resp_exit)
            except Exception:
                logger.exception("Broker exit order failed for %s", trade.security)
                raise
