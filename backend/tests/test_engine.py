"""回测引擎单元测试。"""
import pandas as pd
import pytest

from app.backtest.engine import runBacktest
from app.backtest.strategies.base import Strategy
from tests.conftest import makeBars


class AlwaysLongStrategy(Strategy):
    """测试用:始终满仓持有。"""

    name = "always_long"

    def generateSignals(self, bars: pd.DataFrame) -> pd.Series:
        return pd.Series(1, index=bars["date"].values)


class NeverTradeStrategy(Strategy):
    """测试用:始终空仓。"""

    name = "never_trade"

    def generateSignals(self, bars: pd.DataFrame) -> pd.Series:
        return pd.Series(0, index=bars["date"].values)


class TestRunBacktest:
    def test_emptyBarsRaises(self):
        with pytest.raises(ValueError, match="为空"):
            runBacktest(makeBars([]), AlwaysLongStrategy())

    def test_flatMarketBreaksEvenIgnoringFirstDay(self):
        # 价格不变时净值维持 1(首日后满仓但无涨跌,仅首日无仓位)
        bars = makeBars([100.0] * 20)
        bars["open"] = bars["close"]  # 真正平价行情，避免构造器默认的1%日内收益
        result = runBacktest(bars, AlwaysLongStrategy(), feeRate=0.0)
        assert result["equityCurve"][-1]["equity"] == pytest.approx(1.0, abs=1e-3)

    def test_uptrendAlwaysLongProfits(self):
        # 持续上涨 + 始终满仓 → 总收益为正
        bars = makeBars([100 + i for i in range(60)])
        result = runBacktest(bars, AlwaysLongStrategy(), feeRate=0.0)
        assert result["metrics"]["totalReturn"] > 0

    def test_feeReducesReturn(self):
        # 同一策略,有手续费的收益应低于无手续费
        bars = makeBars([100 + i for i in range(60)])
        noFee = runBacktest(bars, AlwaysLongStrategy(), feeRate=0.0)
        withFee = runBacktest(bars, AlwaysLongStrategy(), feeRate=0.001)
        assert withFee["metrics"]["totalReturn"] < noFee["metrics"]["totalReturn"]

    def test_neverTradeKeepsEquityFlat(self):
        bars = makeBars([100 + i * 0.5 for i in range(30)])
        result = runBacktest(bars, NeverTradeStrategy(), feeRate=0.0)
        assert all(p["equity"] == pytest.approx(1.0, abs=1e-6) for p in result["equityCurve"])
        assert result["metrics"]["totalTrades"] == 0

    def test_outputStructure(self):
        bars = makeBars([100.0, 101.0, 99.0, 102.0, 103.0])
        result = runBacktest(bars, AlwaysLongStrategy())
        assert set(result.keys()) == {"equityCurve", "metrics", "trades", "positions"}
        assert len(result["equityCurve"]) == len(bars)
