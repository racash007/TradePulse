from dataclasses import dataclass
from typing import Optional, List

import pandas as pd

from app.model.SignalType import SignalType


@dataclass
class Signal:
    index: int
    price: float
    date: Optional[pd.Timestamp]
    type: SignalType
    symbol: Optional[str]
    color: Optional[str]
    inside_fvg: bool
    inside_sonar: bool
    fvg_alpha: Optional[float]
    signalStrength: int
    source_strategy: List[str]