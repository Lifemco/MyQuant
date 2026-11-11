"""绩效指标单元测试。"""
import pandas as pd
import pytest

from app.backtest.metrics import computeMetrics, extractTrades
from tests.conftest import makeBars


class TestComputeMetrics:
    def test_constantEquityHasZeroReturn(self):
        # 净值不变时收益为 0,回撤为 0
        equity = pd.Series([1.0] * 10, index=pd.bdate_range("2024-01-01", periods=10))
        positions = pd.Series([0] * 10, index=equity.index)
        m = computeMetrics(equity, positions)
        assert m["totalReturn"] == 0.0
        assert m["maxDrawdown"] == 0.0
        assert m["totalTrades"] == 0

    def test_steadyGrowthHasPositiveReturnAndNoDrawdown(self):
        # 每日涨 1%:总收益为正,无回撤
        equity = pd.Series(
            [1.01**i for i in range(50)], index=pd.bdate_range("2024-01-01", periods=50)
        )
        positions = pd.Series([1] * 50, index=equity.index)
        m = computeMetrics(equity, positions)
        assert m["totalReturn"] > 0
        assert m["annualReturn"] > 0
        assert m["maxDrawdown"] == 0.0
        assert m["sharpeRatio"] > 0

    def test_drawdownIsCaptured(self):
        # 净值先翻倍再腰斩:最大回撤应为 -50%
        equity = pd.Series(
            [1.0, 2.0, 1.0], index=pd.bdate_range("2024-01-01", periods=3)
        )
        positions = pd.Series([1, 1, 1], index=equity.index)
        m = computeMetrics(equity, positions)
        assert m["maxDrawdown"] == pytest.approx(-0.5, abs=1e-4)

    def test_emptyEquityReturnsZeros(self):
        equity = pd.Series([1.0], index=pd.bdate_range("2024-01-01", periods=1))
        positions = pd.Series([0], index=equity.index)
        m = computeMetrics(equity, positions)
        assert m["totalReturn"] == 0.0


class TestExtractTrades:
    def test_singleRoundTrip(self):
        dates = pd.bdate_range("2024-01-01", periods=4)
        positions = pd.Series([0, 1, 1, 0], index=dates)
        equity = pd.Series([1.0, 1.0, 1.1, 1.21], index=dates)
        trades = extractTrades(positions, equity)
        assert len(trades) == 1
        assert trades[0]["entryDate"] == str(dates[1].date())
        assert trades[0]["exitDate"] == str(dates[3].date())
        assert trades[0]["pnlPct"] == pytest.approx(0.21, abs=1e-4)

    def test_openPositionAtEndHasNoExitDate(self):
        dates = pd.bdate_range("2024-01-01", periods=3)
        positions = pd.Series([0, 1, 1], index=dates)
        equity = pd.Series([1.0, 1.0, 1.05], index=dates)
        trades = extractTrades(positions, equity)
        assert len(trades) == 1
        assert trades[0]["exitDate"] is None
