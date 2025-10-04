from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):

    @abstractmethod
    def run(self, df: pd.DataFrame):
        pass

    @abstractmethod
    def plot(self, df: pd.DataFrame, title: str = "Strategy Plot"):
        pass