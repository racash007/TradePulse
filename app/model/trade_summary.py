"""
TradeSummary dataclass for trade execution results.
"""
from dataclasses import dataclass


@dataclass
class TradeSummary:
    """Summary of trade execution results."""
    initial_capital: float
    final_balance: float
    final_pnl: float
    num_trades: int
    wins: int
    losses: int
    win_rate: float
    current_winning_streak: int
    current_losing_streak: int
    max_winning_streak: int
    max_losing_streak: int

    def to_dict(self) -> dict:
        """Convert to dictionary for UI display."""
        return {
            'Initial Capital': self.initial_capital,
            'Final Balance': self.final_balance,
            'Final PnL': self.final_pnl,
            'Number of Trades': self.num_trades,
            'Wins': self.wins,
            'Losses': self.losses,
            'Win Rate (%)': round(self.win_rate, 2),
            'Current Winning Streak': self.current_winning_streak,
            'Current Losing Streak': self.current_losing_streak,
            'Max Winning Streak': self.max_winning_streak,
            'Max Losing Streak': self.max_losing_streak
        }