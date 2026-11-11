"""RSI 均值回归策略:RSI 跌破超卖线买入,涨破超买线卖出。"""
import pandas as pd

from app.backtest.strategies.base import Strategy


def _rsi(close: pd.Series, window: int) -> pd.Series:
    """Wilder 平滑 RSI。"""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / window, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / window, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    return 100 - 100 / (1 + rs)


class RsiReversionStrategy(Strategy):
    name = "rsi_reversion"
    label = "RSI 均值回归"
    desc = "RSI 跌破超卖线买入,涨破超买线卖出;震荡市适用"
    paramsSchema = {
        "window": {"type": "int", "default": 14, "min": 2, "max": 60, "desc": "RSI 周期"},
        "oversold": {"type": "float", "default": 30, "min": 5, "max": 50, "desc": "超卖阈值"},
        "overbought": {"type": "float", "default": 70, "min": 50, "max": 95, "desc": "超买阈值"},
    }

    def generateSignals(self, bars: pd.DataFrame) -> pd.Series:
        window = int(self.params.get("window", 14))
        oversold = float(self.params.get("oversold", 30))
        overbought = float(self.params.get("overbought", 70))
        rsi = _rsi(bars["close"], window)
        # 状态机:低于超卖置 1,高于超购置 0,其余延续上一状态
        raw = pd.Series(float("nan"), index=bars.index)
        raw[rsi < oversold] = 1.0
        raw[rsi > overbought] = 0.0
        signal = raw.ffill().fillna(0).astype(int)
        signal.index = bars["date"].values
        return signal
