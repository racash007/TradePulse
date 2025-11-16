"""
Signal processing utilities for extracting and normalizing signals from strategies.
"""
from typing import List, Dict, Any, Tuple, Optional
from app.model.signal import Signal


def normalize_raw_signal(s) -> Optional[Dict[str, Any]]:
    """
    Normalize a raw signal from either Signal object or dict format.
    Returns a dict with idx, price, typ, color, source or None if invalid.
    """
    if hasattr(s, 'index'):
        idx = int(s.index)
        price = float(s.price) if s.price is not None else None
        typ = getattr(s, 'type', None)
        color = getattr(s, 'color', None)
        source = 'SignalObject'
    elif isinstance(s, dict):
        idx = int(s.get('index')) if s.get('index') is not None else None
        price = float(s.get('price')) if s.get('price') is not None else None
        typ = s.get('type') or s.get('signal')
        color = s.get('color')
        source = 'SignalDict'
    else:
        return None

    if idx is None or price is None:
        return None

    return {
        'idx': idx,
        'price': price,
        'typ': typ,
        'color': color,
        'source': source
    }


def is_buy_signal(typ: str) -> bool:
    """Check if signal type indicates a buy signal."""
    typ_str = str(typ).lower() if typ is not None else ''
    return 'bull' in typ_str or 'buy' in typ_str


def is_sell_signal(typ: str) -> bool:
    """Check if signal type indicates a sell signal."""
    typ_str = str(typ).lower() if typ is not None else ''
    return 'bear' in typ_str or 'sell' in typ_str


def point_in_box(idx: int, price: float, box: dict) -> bool:
    """
    Check if a point (idx, price) is inside a box.
    Box is defined by left, right (index range) and top, bottom (price range).
    """
    if box is None:
        return False
    left = box.get('left', -9999)
    right = box.get('right', 9999)
    top = box.get('top')
    bottom = box.get('bottom')
    try:
        idx_ok = (idx >= left) and (idx <= right)
        price_ok = (top is not None and bottom is not None and price <= top and price >= bottom)
        return idx_ok and price_ok
    except Exception:
        return False


def collect_signals_from_strategies(strategies: List) -> List:
    """
    Collect raw signals from all strategies.
    """
    raw_signals = []
    for strategy in strategies:
        try:
            raw_signals.extend(strategy.get_signals() or [])
        except Exception:
            pass
    return raw_signals


def run_all_strategies(strategies: List, df) -> None:
    """
    Run all strategies on the given DataFrame.
    """
    for strategy in strategies:
        strategy.run(df)