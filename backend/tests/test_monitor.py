"""信号监控服务单元测试。"""
from app.backtest.strategies import getStrategy
from app.monitor.service import computeSignalMarkers, summarizeBars
from tests.conftest import makeBars


class _FixedStrategy:
    """测试用固定信号序列策略,绕过行情推导。"""

    def __init__(self, pattern: list[int]) -> None:
        self.pattern = pattern

    def generateSignals(self, bars):
        import pandas as pd

        assert len(self.pattern) == len(bars)
        return pd.Series(self.pattern, index=bars["date"].values)


def test_buyAndSellMarkers():
    # 0→1 记买入,1→0 记卖出
    bars = makeBars([100.0, 101.0, 102.0, 103.0, 104.0])
    strategy = _FixedStrategy([0, 1, 1, 0, 0])
    result = computeSignalMarkers(bars, strategy)
    assert [m["type"] for m in result["markers"]] == ["buy", "sell"]
    assert result["markers"][0]["price"] == 101.0  # 信号日收盘价
    assert result["holding"] is False
    assert result["lastSignal"]["type"] == "sell"


def test_holdingWhenLatestSignalIsLong():
    bars = makeBars([100.0, 101.0, 102.0])
    result = computeSignalMarkers(bars, _FixedStrategy([0, 1, 1]))
    assert result["holding"] is True
    assert result["lastSignal"]["type"] == "buy"


def test_noTradeHasNoMarkers():
    bars = makeBars([100.0, 100.0, 100.0])
    result = computeSignalMarkers(bars, _FixedStrategy([0, 0, 0]))
    assert result["markers"] == []
    assert result["lastSignal"] is None


def test_realStrategyIntegration():
    # 持续上涨行情下双均线末端应为持仓状态
    bars = makeBars([100 + i for i in range(80)])
    strategy = getStrategy("sma_cross", fastWindow=5, slowWindow=20)
    result = computeSignalMarkers(bars, strategy)
    assert result["holding"] is True
    assert result["markers"][0]["type"] == "buy"


def test_summarizeBars():
    bars = makeBars([100.0, 110.0])
    summary = summarizeBars(bars)
    assert summary["close"] == 110.0
    assert summary["changePct"] == 0.1

    empty = makeBars([])
    assert summarizeBars(empty) == {"close": None, "changePct": None}
