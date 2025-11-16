from dataclasses import dataclass, field
from datetime import timedelta
from enum import IntEnum
from typing import Optional

import pandas as pd

from app.model.OutcomeType import OutcomeType
from app.model.SignalType import SignalType


class SignalStrength(IntEnum):
    NONE = 0
    WEAK = 1
    MODERATE = 2
    STRONG = 3
    VERY_STRONG = 4
    EXTREME = 5


@dataclass
class Trade:
    entry_index: int
    entry_date: Optional[pd.Timestamp]
    exit_date: Optional[pd.Timestamp]
    side: SignalType
    entry_price: float
    exit_price: float
    shares: int
    pnl: float
    security: str
    outcome: OutcomeType
    signalStrength: SignalStrength
    cash_before: float
    cash_after: float
    money_allocated: float = field(init=False)
    lockin_period: Optional[timedelta] = field(init=False)

    def __post_init__(self):
        """Calculate derived fields after initialization."""
        self.money_allocated = self.shares * self.entry_price

        if self.entry_date is not None and self.exit_date is not None:
            self.lockin_period = self.exit_date - self.entry_date
        else:
            self.lockin_period = None



