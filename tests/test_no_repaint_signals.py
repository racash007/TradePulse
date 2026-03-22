import pandas as pd

from app.model.box import Box, BoxType
from app.strategy.fvgorderblocks import FVGOrderBlocks


def test_fvg_bull_signal_not_backdated():
    df = pd.DataFrame(
        {
            'Open': [100.0, 101.0, 106.0],
            'High': [102.0, 103.0, 108.0],
            'Low': [99.0, 100.0, 106.0],
            'Close': [101.0, 102.0, 107.0],
        },
        index=pd.date_range('2025-01-01', periods=3, freq='D')
    )

    s = FVGOrderBlocks(show_signal=True)
    s.bull_boxes = [
        Box(
            left=0,
            right=2,
            top=105.0,
            bottom=95.0,
            box_type=BoxType.BULL,
        )
    ]

    s._process_bull_boxes(df, idx=2, isBull_gap=False)

    assert len(s.signals) == 1
    sig = s.signals[0]
    assert sig.index == 2
    assert sig.price == df['Close'].iat[2]


def test_fvg_bear_signal_not_backdated():
    df = pd.DataFrame(
        {
            'Open': [100.0, 101.0, 98.0],
            'High': [103.0, 102.0, 97.0],
            'Low': [98.0, 96.0, 90.0],
            'Close': [101.0, 97.0, 92.0],
        },
        index=pd.date_range('2025-01-01', periods=3, freq='D')
    )

    s = FVGOrderBlocks(show_signal=True)
    s.bear_boxes = [
        Box(
            left=0,
            right=2,
            top=110.0,
            bottom=100.0,
            box_type=BoxType.BEAR,
        )
    ]

    s._process_bear_boxes(df, idx=2, isBear_gap=False)

    assert len(s.signals) == 1
    sig = s.signals[0]
    assert sig.index == 2
    assert sig.price == df['Close'].iat[2]
