"""
Box dataclass for order block representation.
"""
from dataclasses import dataclass
from typing import Optional
from enum import StrEnum


class BoxType(StrEnum):
    BULL = "bull"
    BEAR = "bear"
    TEMP_BULL = "temp_bull"
    TEMP_BEAR = "temp_bear"
    BULLISH = "bullish"
    BEARISH = "bearish"


@dataclass
class Box:
    """Represents an order block box."""
    left: int
    right: int
    top: float
    bottom: float
    box_type: BoxType
    alpha: float = 0.25
    border_color: Optional[str] = None
    bg_color: Optional[str] = None
    border_width: int = 1
    broken: bool = False
    percent: Optional[float] = None
    created_at: Optional[int] = None

    def contains_point(self, idx: int, price: float) -> bool:
        """Check if a point (idx, price) is inside this box."""
        idx_ok = (idx >= self.left) and (idx <= self.right)
        price_ok = (price <= self.top) and (price >= self.bottom)
        return idx_ok and price_ok

    def to_dict(self) -> dict:
        """Convert to dictionary for backwards compatibility."""
        return {
            'left': self.left,
            'right': self.right,
            'top': self.top,
            'bottom': self.bottom,
            'type': self.box_type.value,
            'alpha': self.alpha,
            'border_color': self.border_color,
            'bg_color': self.bg_color,
            'border_width': self.border_width,
            'broken': self.broken,
            'percent': self.percent,
            'created_at': self.created_at
        }