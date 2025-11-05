class Signal:
    def __init__(self, index, price, type_, symbol=None, color=None):
        self.index = index
        self.price = price
        self.type = type_  # e.g. 'bullish', 'bearish', 'buy', 'sell'
        self.symbol = symbol
        self.color = color

    def as_tuple(self):
        return (self.index, self.price, self.type, self.symbol, self.color)

    def __repr__(self):
        return f"Signal(index={self.index}, price={self.price}, type={self.type}, symbol={self.symbol}, color={self.color})"

