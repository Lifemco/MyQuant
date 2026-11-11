"""策略信号单元测试。"""
import pytest

from app.backtest.strategies import getStrategy, listStrategies
from tests.conftest import makeBars


class TestRegistry:
    def test_listContainsBuiltinStrategies(self):
        names = [s["name"] for s in listStrategies()]
        assert "sma_cross" in names
        assert "rsi_reversion" in names

    def test_unknownStrategyRaises(self):
        with pytest.raises(KeyError):
            getStrategy("not_exist")


class TestSmaCross:
    def test_invalidWindowRaises(self):
        with pytest.raises(ValueError):
            getStrategy("sma_cross", fastWindow=20, slowWindow=5)

    def test_strongUptrendEventuallyLong(self):
        # 稳定上涨后快线必然高于慢线
        bars = makeBars([100 + i for i in range(60)])
        signal = getStrategy("sma_cross", fastWindow=5, slowWindow=20).generateSignals(bars)
        assert signal.iloc[-1] == 1

    def test_signalIsBinary(self):
        bars = makeBars([100 + (i % 7) for i in range(60)])
        signal = getStrategy("sma_cross").generateSignals(bars)
        assert set(signal.unique()).issubset({0, 1})


class TestRsiReversion:
    def test_binarySignals(self):
        bars = makeBars([100 + (i % 5) * 2 for i in range(80)])
        signal = getStrategy("rsi_reversion").generateSignals(bars)
        assert set(signal.unique()).issubset({0, 1})

    def test_continuousCrashTriggersBuy(self):
        # 持续下跌 RSI 趋近 0,必然触发超卖买入
        bars = makeBars([200 - i for i in range(60)])
        signal = getStrategy("rsi_reversion", window=14, oversold=30).generateSignals(bars)
        assert signal.iloc[-1] == 1
