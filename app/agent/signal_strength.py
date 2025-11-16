"""
Signal strength calculation based on FVG and Sonar box inclusion.
"""
from typing import Optional, Tuple


def calculate_signal_strength(
    inside_fvg: bool,
    inside_sonar: bool,
    fvg_alpha: Optional[float],
    dark_alpha_threshold: float = 0.4
) -> int:
    """
    Calculate signal strength based on FVG and Sonar inclusion.

    Rules:
    - buy/sell inside light-green FVG block -> signalStrength = 1
    - buy/sell inside dark-green FVG block  -> signalStrength = 2
    - buy/sell inside light-green FVG block AND Sonarlab block -> 3
    - buy/sell inside dark-green FVG block AND Sonarlab block  -> 4
    - sonar-only -> 1
    - neither -> 0
    """
    if inside_fvg and not inside_sonar:
        # only FVG
        if fvg_alpha is not None and fvg_alpha >= dark_alpha_threshold:
            return 2
        else:
            return 1
    elif inside_fvg and inside_sonar:
        # both
        if fvg_alpha is not None and fvg_alpha >= dark_alpha_threshold:
            return 4
        else:
            return 3
    elif inside_sonar and not inside_fvg:
        # sonar-only fallback
        return 1
    else:
        # neither inside
        return 0


def check_fvg_inclusion(
    idx: int,
    price: float,
    is_buy: bool,
    fvg_strategy
) -> Tuple[bool, Optional[float]]:
    """
    Check if signal is inside an FVG box and return inclusion status and alpha.
    """
    inside_fvg = False
    fvg_alpha = None
    boxes = fvg_strategy.bull_boxes if is_buy else fvg_strategy.bear_boxes

    for box in boxes:
        # Support both Box dataclass and dict
        if hasattr(box, 'contains_point'):
            if box.contains_point(idx, price):
                inside_fvg = True
                fvg_alpha = box.alpha
                break
        else:
            # Legacy dict support
            from app.agent.signal_processor import point_in_box
            if point_in_box(idx, price, box):
                inside_fvg = True
                fvg_alpha = box.get('alpha', None)
                break

    return inside_fvg, fvg_alpha


def check_sonar_inclusion(
    idx: int,
    price: float,
    is_buy: bool,
    sonar_strategy
) -> bool:
    """
    Check if signal is inside a Sonar box.
    """
    boxes = sonar_strategy.long_boxes if is_buy else sonar_strategy.short_boxes

    for box in boxes:
        # Support both Box dataclass and dict
        if hasattr(box, 'contains_point'):
            if box.contains_point(idx, price):
                return True
        else:
            # Legacy dict support
            from app.agent.signal_processor import point_in_box
            if point_in_box(idx, price, box):
                return True

    return False