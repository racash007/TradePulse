from typing import Optional

import pandas as pd

from app.model import Trade, Signal
from app.model.portfolio import Position


def check_position_exit(
        self,
        df: pd.DataFrame,
        signal: Signal,
        position: Position
) -> Optional[Trade]:
    """Check if current signal date triggers exit for existing position."""
    # This would be used for real-time checking
    # For backtesting, exits are handled in _simulate_exit
    return None


def is_long_signal(self, signal_type) -> bool:
    """Determine if signal is a long (buy) signal."""
    if hasattr(signal_type, 'value'):
        return signal_type.value == 'buy'
    type_str = str(signal_type).lower()
    return 'buy' in type_str or 'bull' in type_str