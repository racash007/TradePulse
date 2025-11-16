"""
Portfolio and Position dataclasses for tracking open positions.
"""
from dataclasses import dataclass, field
from typing import Dict, Optional
import pandas as pd


@dataclass
class Position:
    """Represents an open position in a security."""
    security: str
    shares: int
    entry_price: float
    entry_date: Optional[pd.Timestamp]
    entry_index: int
    money_allocated: float
    stop_loss: float
    target: float
    signal_strength: int

    @property
    def current_value(self) -> float:
        """Get the value at entry price."""
        return self.shares * self.entry_price


@dataclass
class Portfolio:
    """Tracks all open positions and capital usage."""
    positions: Dict[str, Position] = field(default_factory=dict)
    total_capital_used: float = 0.0

    def add_position(self, position: Position):
        """Add a new position to the portfolio."""
        self.positions[position.security] = position
        self.total_capital_used += position.money_allocated

    def remove_position(self, security: str) -> Optional[Position]:
        """Remove and return a position from the portfolio."""
        if security in self.positions:
            position = self.positions.pop(security)
            self.total_capital_used -= position.money_allocated
            return position
        return None

    def has_position(self, security: str) -> bool:
        """Check if we have an open position in a security."""
        return security in self.positions

    def get_position(self, security: str) -> Optional[Position]:
        """Get position for a security if it exists."""
        return self.positions.get(security)

    def get_all_positions(self) -> list:
        """Get all open positions as a list."""
        return list(self.positions.values())

    def to_dataframe(self) -> pd.DataFrame:
        """Convert open positions to a DataFrame for display."""
        if not self.positions:
            return pd.DataFrame()

        rows = []
        for security, pos in self.positions.items():
            rows.append({
                'security': security,
                'shares': pos.shares,
                'entry_price': pos.entry_price,
                'entry_date': pos.entry_date,
                'money_allocated': pos.money_allocated,
                'stop_loss': pos.stop_loss,
                'target': pos.target,
                'signal_strength': pos.signal_strength,
                'current_value': pos.current_value
            })

        return pd.DataFrame(rows)

    def summary(self) -> dict:
        """Get portfolio summary."""
        return {
            'Number of Open Positions': len(self.positions),
            'Total Capital Used': self.total_capital_used,
            'Securities Held': ', '.join(self.positions.keys()) if self.positions else 'None'
        }