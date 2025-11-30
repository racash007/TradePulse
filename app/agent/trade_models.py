from dataclasses import dataclass
from typing import Optional
import pandas as pd


@dataclass
class AgentTrade:
    """Record of a completed trade executed by TradeAgent."""
    symbol: str
    direction: str  # 'BUY' or 'SELL'
    entry_date: Optional[pd.Timestamp]
    exit_date: Optional[pd.Timestamp]
    entry_price: float
    exit_price: float
    shares: int
    money_allocated: float
    pnl: float
    cash_before: float
    cash_after: float


@dataclass
class AgentPosition:
    """Representation of an open position."""
    symbol: str
    direction: str
    entry_date: Optional[pd.Timestamp]
    entry_index: int
    entry_price: float
    shares: int
    money_allocated: float
    stop_loss: float
    target: float
    signal_strength: int
    exit_idx: Optional[int] = None
    exit_date: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    proceeds: Optional[float] = None
    cash_before: Optional[float] = None

