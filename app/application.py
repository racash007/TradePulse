from app.strategy.fvgorderblocks import FVGOrderBlocks
from app.strategy.sonarlaborderblocks import SonarlabOrderBlocks
from app.utility.utility import load_data

if __name__ == "__main__":
    # create a dummy dataset
    df = load_data("BAJAJFINSV")

    # 1) FVG Order Blocks (BigBeluga)
    fvg = FVGOrderBlocks(
        filter_gap=0.52,   # same default you had shown earlier in sample
        show_imb=True,
        box_amount=10,
        show_broken=False,
        show_signal=True,
        col_bull="#14be94",
        col_bear="#C21919",
        lookback=2000
    )
    fvg.run(df)
    # Now plot - shows candlesticks, permanent and temporary boxes, and labels
    fvg.plot(df, title="FVG Order Blocks [BigBeluga] (Python translation)")

    # 2) Sonarlab - Order Blocks
    son = SonarlabOrderBlocks(
        sensitivity=28,
        OBMitigationType="Close",
        col_bullish="#5db49e",
        col_bullish_ob="#64C4AC",
        col_bearish="#4760bb",
        col_bearish_ob="#506CD3",
        buy_alert=True,
        sell_alert=True
    )
    son.run(df)
    son.plot(df, title="Sonarlab - Order Blocks (Python translation)")
