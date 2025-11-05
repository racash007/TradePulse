from typing import List, Dict, Any
import pandas as pd

# resilient import for EnhancedSignal if package vs script
try:
    from app.agent.signal_generator import EnhancedSignal
except Exception:
    import importlib
    _candidates = [
        'app.agent.signal_generator',
        'agent.signal_generator',
        'app.agent.signal_generator',
        'strategy.signal_generator',
        'signal_generator',
        'app.signal_generator'
    ]
    EnhancedSignal = None
    for _m in _candidates:
        try:
            mod = importlib.import_module(_m)
            if hasattr(mod, 'EnhancedSignal'):
                EnhancedSignal = getattr(mod, 'EnhancedSignal')
                break
        except Exception:
            continue
    if EnhancedSignal is None:
        raise ImportError("Could not import EnhancedSignal from any candidate module paths: " + ",".join(_candidates))


class TradeAgent:
    def __init__(self, initial_capital: float = 100000.0, target_pct: float = 0.07, stop_loss_pct: float = 0.03, allocation_step: float = 0.2):
        self.initial_capital = float(initial_capital)
        self.cash = float(initial_capital)
        self.target_pct = float(target_pct)
        self.stop_loss_pct = float(stop_loss_pct)
        # new: allocation fraction per strength unit (e.g. 0.2 -> strength 1 = 20%)
        self.allocation_step = float(allocation_step)
        self.trades: List[Dict[str, Any]] = []
        self.winning_streak = 0
        self.losing_streak = 0
        self.max_winning_streak = 0
        self.max_losing_streak = 0
        self.final_pnl = 0.0

    def allocation_pct(self, strength: int) -> float:
        """Allocation percentage based on signal strength: uses configured allocation_step (cap at 100%)"""
        if strength is None:
            return 0.0
        try:
            pct = self.allocation_step * int(strength)
        except Exception:
            pct = 0.0
        return min(max(pct, 0.0), 1.0)

    def execute_signals(self, df: pd.DataFrame, enhanced_signals: List[EnhancedSignal]) -> pd.DataFrame:
        """
        Execute trades based on enhanced signals and historical price data in df.
        Returns a DataFrame of executed trades (one row per trade) with P&L information.
        """
        self.trades = []
        self.cash = float(self.initial_capital)
        self.final_pnl = 0.0
        self.winning_streak = 0
        self.losing_streak = 0
        self.max_winning_streak = 0
        self.max_losing_streak = 0

        # ensure signals sorted by index (chronological)
        signals = sorted(enhanced_signals, key=lambda s: int(s.index) if hasattr(s, 'index') else 0)

        n = len(df)
        total_wins = 0
        total_losses = 0
        for s in signals:
            try:
                idx = int(s.index)
                entry_price = float(s.price)
                typ = str(s.type).lower() if s.type is not None else ''
                strength = int(s.signalStrength) if s.signalStrength is not None else 0
            except Exception:
                continue

            if strength <= 0:
                continue

            pct = self.allocation_pct(strength)
            alloc_amount = self.cash * pct
            shares = int(alloc_amount // entry_price) if entry_price > 0 else 0

            # determine side (long/short) before modifying cash
            if 'buy' in typ or 'bull' in typ:
                long = True
            else:
                long = False

            if shares <= 0:
                # cannot buy any shares with allocated amount
                continue

            # debit/credit cash for entry depending on side
            cost = shares * entry_price
            cash_before = self.cash
            if long:
                # buy: pay cash now
                self.cash -= cost
            else:
                # short: receive proceeds now
                self.cash += cost

            # compute target and stop prices
            if 'buy' in typ or 'bull' in typ:
                long = True
                tp_price = entry_price * (1.0 + self.target_pct)
                sl_price = entry_price * (1.0 - self.stop_loss_pct)
            else:
                long = False
                # for shorts: target is down by target_pct, stop is up by stop_loss_pct
                tp_price = entry_price * (1.0 - self.target_pct)
                sl_price = entry_price * (1.0 + self.stop_loss_pct)

            exit_price = None
            exit_idx = None
            outcome = 'no_hit'
            # simulate forward bars to find TP or SL
            for i in range(idx + 1, n):
                high = float(df['High'].iat[i])
                low = float(df['Low'].iat[i])
                if long:
                    # check TP first (if within same bar both hit, assume TP if high >= tp)
                    if high >= tp_price:
                        exit_price = tp_price
                        exit_idx = i
                        outcome = 'win'
                        break
                    if low <= sl_price:
                        exit_price = sl_price
                        exit_idx = i
                        outcome = 'loss'
                        break
                else:
                    # short
                    if low <= tp_price:
                        exit_price = tp_price
                        exit_idx = i
                        outcome = 'win'
                        break
                    if high >= sl_price:
                        exit_price = sl_price
                        exit_idx = i
                        outcome = 'loss'
                        break

            if exit_price is None:
                # not hit either by the end; close at last close price
                exit_idx = n - 1
                exit_price = float(df['Close'].iat[exit_idx])
                # outcome based on pnl
                if long:
                    outcome = 'win' if exit_price >= entry_price * (1.0 + 0.000001) and exit_price >= tp_price else ('loss' if exit_price <= sl_price else 'exit')
                else:
                    outcome = 'win' if exit_price <= entry_price * (1.0 - 0.000001) and exit_price <= tp_price else ('loss' if exit_price >= sl_price else 'exit')

            # compute pnl
            if long:
                pnl = shares * (exit_price - entry_price)
            else:
                pnl = shares * (entry_price - exit_price)

            # settle exit depending on side
            proceeds = shares * exit_price
            if long:
                # sell to close: receive proceeds
                self.cash += proceeds
            else:
                # buy to close: pay proceeds
                self.cash -= proceeds
            cash_after = self.cash

            # accumulate final pnl from each trade
            self.final_pnl += pnl

            # update streaks
            if pnl > 0:
                self.winning_streak += 1
                self.losing_streak = 0
                if self.winning_streak > self.max_winning_streak:
                    self.max_winning_streak = self.winning_streak
                total_wins += 1
            else:
                self.losing_streak += 1
                self.winning_streak = 0
                if self.losing_streak > self.max_losing_streak:
                    self.max_losing_streak = self.losing_streak
                total_losses += 1

            trade = {'entry_index': idx, 'entry_date': getattr(s, 'date', None), 'exit_index': exit_idx,
                     'exit_date': df.index[exit_idx] if exit_idx is not None and len(df.index) > exit_idx else None,
                     'side': 'buy' if long else 'sell', 'entry_price': entry_price, 'exit_price': exit_price,
                     'shares': shares, 'pnl': pnl, 'outcome': outcome, 'signalStrength': strength,
                     'cash_before': cash_before, 'cash_after': cash_after}
            # add cash debug info
            self.trades.append(trade)

        # final balance and pnl
        final_balance = self.cash
        final_pnl_total = final_balance - self.initial_capital
        self.final_pnl = final_pnl_total
        self.final_balance = final_balance
        self.total_wins = total_wins
        self.total_losses = total_losses
        self.num_trades = len(self.trades)

        # return DataFrame of trades
        df_trades = pd.DataFrame(self.trades)
        return df_trades

    def get_summary(self) -> Dict[str, Any]:
        """Return a summary dict for UI display."""
        wins = getattr(self, 'total_wins', 0)
        losses = getattr(self, 'total_losses', 0)
        num = getattr(self, 'num_trades', 0)
        win_rate = (wins / num * 100.0) if num > 0 else 0.0
        return {
            'Initial Capital': self.initial_capital,
            'Final Balance': getattr(self, 'final_balance', self.initial_capital),
            'Final PnL': getattr(self, 'final_pnl', 0.0),
            'Number of Trades': num,
            'Wins': wins,
            'Losses': losses,
            'Win Rate (%)': round(win_rate, 2),
            'Current Winning Streak': self.winning_streak,
            'Current Losing Streak': self.losing_streak,
            'Max Winning Streak': self.max_winning_streak,
            'Max Losing Streak': self.max_losing_streak
        }
