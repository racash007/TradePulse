from app.strategy.fvgorderblocks import FVGOrderBlocks
from app.strategy.sonarlaborderblocks import SonarlabOrderBlocks
from app.strategy.strategy import Strategy

class StrategyFactory:
    @staticmethod
    def get_strategy(name: str, **kwargs) -> Strategy:
        name = name.lower()
        if name == "fvgorderblocks":
            return FVGOrderBlocks(**kwargs)
        elif name == "sonarlaborderblocks":
            return SonarlabOrderBlocks(**kwargs)
        else:
            raise ValueError(f"Unknown strategy: {name}")

