"""双均线策略:快线上穿慢线买入,下穿卖出。"""
import pandas as pd

from app.backtest.strategies.base import Strategy


class SmaCrossStrategy(Strategy):
    name = "sma_cross"
    label = "双均线交叉"
    desc = "快线上穿慢线买入,下穿卖出;经典趋势跟随"
    paramsSchema = {
        "fastWindow": {"type": "int", "default": 5, "min": 2, "max": 60, "desc": "快线周期"},
        "slowWindow": {"type": "int", "default": 20, "min": 5, "max": 250, "desc": "慢线周期"},
    }

    def generateSignals(self, bars: pd.DataFrame) -> pd.Series:
        fast = int(self.params.get("fastWindow", 5))
        slow = int(self.params.get("slowWindow", 20))
        if fast >= slow:
            raise ValueError(f"快线周期({fast})必须小于慢线周期({slow})")
        close = bars["close"]
        fastMa = close.rolling(fast).mean()
        slowMa = close.rolling(slow).mean()
        signal = (fastMa > slowMa).astype(int)
        signal.index = bars["date"].values
        return signal
