"""
TradeAgent - Executes trades based on signals and tracks performance with Portfolio.
"""
from typing import List, Optional, override
import pandas as pd
import logging
from app.ui.common import get_force_close_at_end

from app.agent.agent import Agent
from app.model.OutcomeType import OutcomeType
from app.model.SignalType import SignalType
from app.model.trade import Trade, SignalStrength
from app.model.trade_summary import TradeSummary
from app.model.signal import Signal
from app.model.portfolio import Portfolio, Position
from app.utility.signal_util import is_long_signal, check_position_exit

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class PaperTradeAgent(Agent):
    def __init__(
        self,
        initial_capital: float = 100000.0,
        target_pct: float = 0.07,
        stop_loss_pct: float = 0.03,
        allocation_step: float = 0.2
    ):
        self.final_pnl = 0
        self.final_balance = initial_capital
        self.initial_capital = initial_capital
        self.target_pct = target_pct
        self.stop_loss_pct = stop_loss_pct
        self.allocation_step = allocation_step

        # State
        self._reset_state()

    def _reset_state(self):
        """Reset all state variables for a new execution."""
        self.cash = self.initial_capital
        self.trades: List[Trade] = []
        self.portfolio = Portfolio()
        self.winning_streak = 0
        self.losing_streak = 0
        self.max_winning_streak = 0
        self.max_losing_streak = 0
        self.total_wins = 0
        self.total_losses = 0
        self.final_pnl = 0.0
        self.final_balance = self.initial_capital

    def allocation_pct(self, strength: int) -> float:
        """Calculate allocation percentage based on signal strength (capped at 100%)."""
        if strength is None or strength <= 0:
            return 0.0
        pct = self.allocation_step * strength
        return min(pct, 1.0)

    @override
    def execute_signals(self, df: pd.DataFrame, enhanced_signals: List[Signal]) -> pd.DataFrame:
        """
        Execute trades based on enhanced signals and historical price data.
        Returns a DataFrame of executed trades with P&L information.
        """
        self._reset_state()

        # Sort signals chronologically by date
        signals = sorted(enhanced_signals, key=lambda s: s.date if s.date is not None else pd.Timestamp.min)

        # expose df mapping so _process_pending_exits can adjust dates if needed
        self._df_mapping = {signal.symbol: df for signal in signals}

        for signal in signals:
            # Process any pending exits that occur before this signal's date
            logger.debug("Processing pending exits before signal date: %s", signal.date)
            self._process_pending_exits(signal.date)

            logger.debug("Executing signal: %s at index %s price %s", getattr(signal, 'symbol', None), getattr(signal, 'index', None), getattr(signal, 'price', None))
            trade = self._execute_single_trade(df, signal)
            if trade:
                self.trades.append(trade)

        # After processing all signals, optionally force-close remaining positions at last available bar
        if get_force_close_at_end():
            try:
                last_date = df.index[-1]
                logger.debug("Force-closing open positions at end of data: %s", last_date)
                # For each open position, set exit info to last bar close and process exit
                for security, position in list(self.portfolio.positions.items()):
                    # set exit info if not already set
                    if not hasattr(position, 'exit_idx') or position.exit_idx is None:
                        position.exit_idx = len(df.index) - 1
                        position.exit_date = df.index[position.exit_idx]
                        position.exit_price = float(df['Close'].iat[position.exit_idx]) if 'Close' in df.columns else float(df.iat[position.exit_idx, -1])
                        # compute pnl
                        if getattr(position, 'is_long', True):
                            position.pnl = position.shares * (position.exit_price - position.entry_price)
                            position.proceeds = position.shares * position.exit_price
                        else:
                            position.pnl = position.shares * (position.entry_price - position.exit_price)
                            position.proceeds = 0.0
                        position.outcome = OutcomeType.EXIT
                # Now process exits up to last_date
                self._process_pending_exits(last_date)
            except Exception as e:
                logger.exception("Error during forced close: %s", e)

        # Calculate final results (don't close open positions unless forced)
        self.final_balance = self.cash + self.portfolio.total_capital_used
        self.final_pnl = self.final_balance - self.initial_capital

        return self._trades_to_dataframe()

    def _execute_single_trade(self, df: pd.DataFrame, signal: Signal) -> Optional[Trade]:
        """Execute a single trade based on the signal."""
        strength = signal.signalStrength or 0
        if strength <= 0:
            return None

        entry_price = signal.price
        if entry_price <= 0:
            return None

        security = signal.symbol
        is_long = is_long_signal(signal.type)

        # Check if we already have a position in this security
        if self.portfolio.has_position(security):
            # Check if this signal triggers an exit (stop loss or target)
            position = self.portfolio.get_position(security)
            trade =check_position_exit(df, signal, position)
            if trade:
                return trade
            # Otherwise, we already hold this security - skip buying more
            return None

        # Open new position
        return self._open_position(df, signal, entry_price, is_long, strength, security)

    def _open_position(
        self,
        df: pd.DataFrame,
        signal: Signal,
        entry_price: float,
        is_long: bool,
        strength: int,
        security: str
    ) -> Optional[Trade]:
        """Open a new position."""
        # Calculate position size based on available cash
        pct = self.allocation_pct(strength)
        alloc_amount = self.cash * pct

        # For long positions, check we have enough cash
        if is_long:
            if self.cash <= 0:
                return None
            shares = int(alloc_amount // entry_price)
            cost = shares * entry_price
            if cost > self.cash:
                # Reduce shares to fit available cash
                shares = int(self.cash // entry_price)
                cost = shares * entry_price
        else:
            shares = int(alloc_amount // entry_price)
            cost = shares * entry_price

        if shares <= 0:
            return None

        # Calculate target and stop prices
        tp_price, sl_price = self._calculate_exit_prices(entry_price, is_long)

        # Record cash before trade
        cash_before = self.cash

        # Execute entry - deduct cash (this is the capital locked in this trade)
        if is_long:
            self.cash -= cost

        # Check if exit is hit in subsequent bars
        exit_price, exit_idx, outcome = self._simulate_exit(
            df, signal.index, tp_price, sl_price, is_long
        )

        # Map entry index
        try:
            entry_idx = int(signal.index)
        except Exception:
            entry_idx = None

        # If an exit was found, ensure it's strictly after the entry index
        if exit_idx is not None and entry_idx is not None and exit_idx > entry_idx and outcome in [OutcomeType.WIN, OutcomeType.LOSS]:
             # Calculate P&L
             if is_long:
                 pnl = shares * (exit_price - entry_price)
                 proceeds = shares * exit_price
             else:
                 pnl = shares * (entry_price - exit_price)
                 proceeds = 0  # For shorts

             # Create position to track until exit date
             position = Position(
                 security=security,
                 shares=shares,
                 entry_price=entry_price,
                 entry_date=signal.date,
                 entry_index=signal.index,
                 money_allocated=cost,
                 stop_loss=sl_price,
                 target=tp_price,
                 signal_strength=strength
             )
             self.portfolio.add_position(position)

             # Store exit info in position for later processing
             position.exit_idx = exit_idx
             position.exit_date = df.index[exit_idx] if exit_idx < len(df.index) else None
             position.exit_price = exit_price
             position.pnl = pnl
             position.proceeds = proceeds
             position.outcome = outcome
             position.is_long = is_long
             position.cash_before = cash_before

             return None  # Trade will be completed later

         # Position remains open (no exit hit within data range)
         # Add to portfolio for tracking
        position = Position(
             security=security,
             shares=shares,
             entry_price=entry_price,
             entry_date=signal.date,
             entry_index=signal.index,
             money_allocated=cost,
             stop_loss=sl_price,
             target=tp_price,
             signal_strength=strength
         )
        self.portfolio.add_position(position)

        return None



    def _calculate_exit_prices(self, entry_price: float, is_long: bool) -> tuple:
        """Calculate target price and stop loss price."""
        if is_long:
            tp_price = entry_price * (1.0 + self.target_pct)
            sl_price = entry_price * (1.0 - self.stop_loss_pct)
        else:
            tp_price = entry_price * (1.0 - self.target_pct)
            sl_price = entry_price * (1.0 + self.stop_loss_pct)
        return tp_price, sl_price

    def _simulate_exit(
        self,
        df: pd.DataFrame,
        entry_idx: int,
        tp_price: float,
        sl_price: float,
        is_long: bool
    ) -> tuple:
        """Simulate forward bars to find exit point.

        Returns (exit_price, exit_idx, outcome) where exit_idx is an integer index > entry_idx when an exit occurs.
        If no exit is found, returns (None, None, OutcomeType.EXIT) to indicate position remains open.
        """
        n = len(df)

        # No forward bars to inspect
        if entry_idx is None or entry_idx >= n - 1:
            return None, None, OutcomeType.EXIT

        for i in range(int(entry_idx) + 1, n):
            high = df['High'].iat[i]
            low = df['Low'].iat[i]

            if is_long:
                if high >= tp_price:
                    logger.debug("TP hit at idx %s price %s", i, tp_price)
                    return tp_price, i, OutcomeType.WIN
                if low <= sl_price:
                    logger.debug("SL hit at idx %s price %s", i, sl_price)
                    return sl_price, i, OutcomeType.LOSS
            else:
                if low <= tp_price:
                    logger.debug("TP hit (short) at idx %s price %s", i, tp_price)
                    return tp_price, i, OutcomeType.WIN
                if high >= sl_price:
                    logger.debug("SL hit (short) at idx %s price %s", i, sl_price)
                    return sl_price, i, OutcomeType.LOSS

        # No exit hit - keep position open
        return None, None, OutcomeType.EXIT

    def _process_pending_exits(self, current_date):
        """Process any positions that have exits scheduled before current date."""
        # Find positions with pending exits at or before current date
        positions_to_exit = []
        for security, position in list(self.portfolio.positions.items()):
            if hasattr(position, 'exit_date') and position.exit_date is not None:
                # Compare by date, not index
                if current_date is None or position.exit_date <= current_date:
                    positions_to_exit.append((security, position))

        # Sort by exit date to process in chronological order
        positions_to_exit.sort(key=lambda x: x[1].exit_date)

        # Process each exit
        for security, position in positions_to_exit:
            # Defensive: ensure exit_date is after entry_date. If not, try to adjust to next bar.
            try:
                if position.exit_date is not None and position.entry_date is not None:
                    if pd.to_datetime(position.exit_date) <= pd.to_datetime(position.entry_date):
                        # try to adjust using entry_index + 1 if df is available through portfolio owner
                        try:
                            # portfolio may have reference to dataframe mapping via agent attribute
                            df_map = getattr(self, '_df_mapping', None)
                            if df_map and security in df_map:
                                df_local = df_map[security]
                                entry_idx = int(position.entry_index)
                                if entry_idx + 1 < len(df_local.index):
                                    new_idx = entry_idx + 1
                                    position.exit_idx = new_idx
                                    position.exit_date = df_local.index[new_idx]
                                    position.exit_price = float(df_local['Close'].iat[new_idx]) if 'Close' in df_local.columns else float(df_local.iat[new_idx, -1])
                                else:
                                    # fallback: add one day to entry_date if it's a datetime
                                    if hasattr(position.entry_date, 'to_pydatetime'):
                                        position.exit_date = pd.to_datetime(position.entry_date) + pd.Timedelta(days=1)
                        except Exception:
                            # ignore adjustment errors and leave as-is
                            pass
            except Exception:
                pass

            # Return cash from the exit
            if hasattr(position, 'is_long') and position.is_long:
                self.cash += position.proceeds
                logger.debug("Position %s closed; proceeds %s returned to cash", security, position.proceeds)

            # Update streaks
            self._update_streaks(position.pnl)
            logger.debug("Position %s PnL %s updated streaks W:%s L:%s", security, position.pnl, self.winning_streak, self.losing_streak)

            # Create completed Trade object
            trade = Trade(
                entry_index=position.entry_index,
                entry_date=position.entry_date,
                exit_date=position.exit_date,
                side=SignalType.BUY if getattr(position, 'is_long', True) else SignalType.SELL,
                entry_price=position.entry_price,
                exit_price=position.exit_price,
                shares=position.shares,
                pnl=position.pnl,
                security=security,
                outcome=position.outcome,
                signalStrength=SignalStrength(position.signal_strength),
                cash_before=position.cash_before,
                cash_after=self.cash
            )
            self.trades.append(trade)

            # Remove from portfolio
            self.portfolio.remove_position(security)

    def _update_streaks(self, pnl: float):
        """Update winning/losing streaks based on trade P&L."""
        if pnl > 0:
            self.winning_streak += 1
            self.losing_streak = 0
            self.max_winning_streak = max(self.max_winning_streak, self.winning_streak)
            self.total_wins += 1
        else:
            self.losing_streak += 1
            self.winning_streak = 0
            self.max_losing_streak = max(self.max_losing_streak, self.losing_streak)
            self.total_losses += 1

    def _trades_to_dataframe(self) -> pd.DataFrame:
        """Convert trades list to DataFrame."""
        if not self.trades:
            return pd.DataFrame()

        rows = []
        for trade in self.trades:
            rows.append({
                'entry_index': trade.entry_index,
                'entry_date': trade.entry_date,
                'exit_date': trade.exit_date,
                'side': trade.side.value if hasattr(trade.side, 'value') else trade.side,
                'entry_price': trade.entry_price,
                'exit_price': trade.exit_price,
                'shares': trade.shares,
                'pnl': trade.pnl,
                'security': trade.security,
                'outcome': trade.outcome.value if hasattr(trade.outcome, 'value') else trade.outcome,
                'signalStrength': trade.signalStrength.value if hasattr(trade.signalStrength, 'value') else trade.signalStrength,
                'cash_before': trade.cash_before,
                'cash_after': trade.cash_after,
                'money_allocated': trade.money_allocated,
                'lockin_period': trade.lockin_period
            })

        return pd.DataFrame(rows)

    def get_summary(self) -> TradeSummary:
        """Return a TradeSummary object with execution results."""
        num_trades = len(self.trades)
        win_rate = (self.total_wins / num_trades * 100.0) if num_trades > 0 else 0.0

        return TradeSummary(
            initial_capital=self.initial_capital,
            final_balance=self.final_balance,
            final_pnl=self.final_pnl,
            num_trades=num_trades,
            wins=self.total_wins,
            losses=self.total_losses,
            win_rate=win_rate,
            current_winning_streak=self.winning_streak,
            current_losing_streak=self.losing_streak,
            max_winning_streak=self.max_winning_streak,
            max_losing_streak=self.max_losing_streak
        )

    def get_portfolio(self) -> Portfolio:
        """Return the current portfolio with open positions."""
        return self.portfolio

    def force_close_open_positions(self, file_df_mapping: Optional[dict] = None) -> None:
        """Force-close all open positions using the last available bar from the provided dataframes.

        file_df_mapping: dict mapping security -> dataframe. If not provided, uses self._df_mapping if available.
        This sets exit_idx, exit_date, exit_price, pnl, proceeds, outcome for each open position and
        leaves actual finalization to _process_pending_exits.
        """
        df_map = file_df_mapping or getattr(self, '_df_mapping', None)
        # compute last date per security if df_map given
        for security, position in list(self.portfolio.positions.items()):
            # only force-close positions that do not already have an exit
            if hasattr(position, 'exit_idx') and position.exit_idx is not None:
                continue
            try:
                if df_map and security in df_map:
                    df_local = df_map[security]
                    last_idx = len(df_local.index) - 1
                    if last_idx >= 0:
                        position.exit_idx = last_idx
                        position.exit_date = df_local.index[last_idx]
                        position.exit_price = float(df_local['Close'].iat[last_idx]) if 'Close' in df_local.columns else float(df_local.iat[last_idx, -1])
                else:
                    # no df available for this security; set exit_date to a sentinel (today) and use entry price as exit
                    position.exit_idx = None
                    position.exit_date = pd.Timestamp.now()
                    position.exit_price = position.entry_price

                # compute pnl and proceeds
                if getattr(position, 'is_long', True):
                    position.pnl = position.shares * (position.exit_price - position.entry_price)
                    position.proceeds = position.shares * position.exit_price
                else:
                    position.pnl = position.shares * (position.entry_price - position.exit_price)
                    position.proceeds = 0.0

                # mark outcome as EXIT (forced)
                position.outcome = OutcomeType.EXIT
            except Exception as e:
                logger.exception("Failed to force-close position %s: %s", security, e)
