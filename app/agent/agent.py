from abc import ABC, abstractmethod
from typing import List

import pandas as pd

from app.model.signal import Signal


class Agent(ABC):

    @abstractmethod
    def execute_signals(self, df: pd.DataFrame, enhanced_signals: List[Signal]) -> pd.DataFrame:
        """Run the strategy on the given DataFrame."""
        pass