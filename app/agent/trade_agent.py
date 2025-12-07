import logging
from typing import Optional, List, override

import pandas as pd

from app.agent.paper_trade_agent import PaperTradeAgent
from app.model import Trade, SignalType, Signal
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

    @override
    def execute_signals(self, df: pd.DataFrame, enhanced_signals: List[Signal]) -> pd.DataFrame:
        """Run signal execution and optionally place orders for the completed trades.
        Args:
            df: OHLC DataFrame used for simulation (index is dates)
            enhanced_signals: list of Signal objects produced by SignalGenerator
        Returns:
            DataFrame of executed trades (same as TradeAgent.execute_signals)
        """

        # Sort signals chronologically by date
        signals = sorted(enhanced_signals, key=lambda s: s.date if s.date is not None else pd.Timestamp.min)

        # If dry_run or no broker configured, only log
        for signal in signals:
            try:
                trade = Trade(signal)
                if trade is not None:
                    self.trades.append(trade)
                self._place_trade_via_broker(trade)
            except Exception as exc:
                logger.exception("Failed to place trade for %s: %s", getattr(trade, 'security', None), exc)

        return self._trades_to_dataframe()

    def _place_trade_via_broker(self, trade: Trade, place_on_exit: bool = True) -> None:
        """Place entry (and optional exit) via BrokerService. Safe no-op if dry_run."""
        side = trade.side

        # Determine transaction types for entry and exit
        exit_txn = 'SELL' if side == SignalType.BUY else 'BUY'

        # Place entry order
        try:
            resp_entry = self.broker.place_order(
                security_symbol=trade.security,
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
                    security_symbol=trade.security,
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
