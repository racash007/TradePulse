import pandas as pd

from app.model.box import Box, BoxType
from app.strategy.sonarlaplaceorderblocks import SonarlaplaceOrderBlocks


def test_sonar_buy_signal_uses_close_price_not_low():
    df = pd.DataFrame(
        {
            'Open': [114.0],
            'High': [116.0],
            'Low': [109.0],
            'Close': [113.5],
        },
        index=pd.date_range('2025-02-28', periods=1, freq='D')
    )

    s = SonarlaplaceOrderBlocks(buy_alert=True, sell_alert=False)
    s.long_boxes = [
        Box(left=0, right=0, top=112.0, bottom=108.0, box_type=BoxType.BULLISH)
    ]

    mitigation = pd.Series([float('nan')])
    s._process_bullish_obs(df, idx=0, OBBullMitigation=mitigation)

    assert len(s.signals) == 1
    sig = s.signals[0]
    assert sig.price == df['Close'].iat[0]
