"""
TradeAgent - Executes trades based on signals and tracks performance with Portfolio.
"""
from typing import List, Optional
import pandas as pd

from app.model.OutcomeType import OutcomeType
from app.model.SignalType import SignalType
from app.model.trade import Trade, SignalStrength
from app.model.trade_summary import TradeSummary
from app.model.signal import Signal
from app.model.portfolio import Portfolio, Position


class TradeAgent:
    def __init__(
        self,
        initial_capital: float = 100000.0,
        target_pct: float = 0.07,
        stop_loss_pct: float = 0.03,
        allocation_step: float = 0.2
    ):
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

    def execute_signals(self, df: pd.DataFrame, enhanced_signals: List[Signal]) -> pd.DataFrame:
        """
        Execute trades based on enhanced signals and historical price data.
        Returns a DataFrame of executed trades with P&L information.
        """
        self._reset_state()

        # Sort signals chronologically by date
        signals = sorted(enhanced_signals, key=lambda s: s.date if s.date is not None else pd.Timestamp.min)

        for signal in signals:
            # Process any pending exits that occur before this signal's date
            self._process_pending_exits(signal.date)

            trade = self._execute_single_trade(df, signal)
            if trade:
                self.trades.append(trade)

        # Calculate final results (don't close open positions)
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
        is_long = self._is_long_signal(signal.type)

        # Check if we already have a position in this security
        if self.portfolio.has_position(security):
            # Check if this signal triggers an exit (stop loss or target)
            position = self.portfolio.get_position(security)
            trade = self._check_position_exit(df, signal, position)
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

        # Get exit date
        exit_date = df.index[exit_idx] if exit_idx < len(df.index) else None

        # If exit was found within data range, create a pending trade
        # The cash will be returned when we process signals at or after the exit date
        if outcome in [OutcomeType.WIN, OutcomeType.LOSS]:
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
            position.exit_date = exit_date
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

    def _check_position_exit(
        self,
        df: pd.DataFrame,
        signal: Signal,
        position: Position
    ) -> Optional[Trade]:
        """Check if current signal date triggers exit for existing position."""
        # This would be used for real-time checking
        # For backtesting, exits are handled in _simulate_exit
        return None

    def _is_long_signal(self, signal_type) -> bool:
        """Determine if signal is a long (buy) signal."""
        if hasattr(signal_type, 'value'):
            return signal_type.value == 'buy'
        type_str = str(signal_type).lower()
        return 'buy' in type_str or 'bull' in type_str

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
        """Simulate forward bars to find exit point."""
        n = len(df)

        for i in range(entry_idx + 1, n):
            high = df['High'].iat[i]
            low = df['Low'].iat[i]

            if is_long:
                if high >= tp_price:
                    return tp_price, i, OutcomeType.WIN
                if low <= sl_price:
                    return sl_price, i, OutcomeType.LOSS
            else:
                if low <= tp_price:
                    return tp_price, i, OutcomeType.WIN
                if high >= sl_price:
                    return sl_price, i, OutcomeType.LOSS

        # No exit hit - position remains open
        return 0.0, n - 1, OutcomeType.EXIT

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
            # Return cash from the exit
            if hasattr(position, 'is_long') and position.is_long:
                self.cash += position.proceeds

            # Update streaks
            self._update_streaks(position.pnl)

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