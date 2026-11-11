"""S1/S2 策略与批量/寻优接口单元测试。"""
import pytest
from fastapi.testclient import TestClient

from app.backtest.strategies import getStrategy, listStrategies
from app.data.store import saveBars
from app.main import app
from tests.conftest import makeBars

client = TestClient(app)


class TestRegistry:
    def test_s1_s2_registered(self):
        names = [s["name"] for s in listStrategies()]
        assert "s1_trend_ma" in names
        assert "s2_volume_break" in names

    def test_meta_contains_desc(self):
        metas = {s["name"]: s for s in listStrategies()}
        assert "企稳" in metas["s1_trend_ma"]["desc"]


class TestS1TrendMa:
    def test_entryAfterStableDays(self):
        # 先平 30 天 → 再持续上涨:企稳(3 日站上 MA5)后应持仓
        closes = [10.0] * 30 + [10.0 + 0.5 * i for i in range(30)]
        strategy = getStrategy("s1_trend_ma", stableDays=3, exitMa=20)
        signals = strategy.generateSignals(makeBars(closes))
        assert signals.iloc[30] == 0  # 平台期不持仓
        assert signals.iloc[-1] == 1  # 上涨企稳后持仓
        # 企稳应在 3~5 天内确认
        firstLong = signals[signals == 1].index[0]
        assert firstLong >= signals.index[32]

    def test_exitBelowExitMa(self):
        # 上涨后暴跌跌破 20 日线 → 清仓
        closes = [10.0] * 10 + [10.0 + 0.3 * i for i in range(30)] + [25.0 - 2.0 * i for i in range(15)]
        strategy = getStrategy("s1_trend_ma", stableDays=3, exitMa=20)
        signals = strategy.generateSignals(makeBars(closes))
        assert signals.iloc[-1] == 0


class TestS2VolumeBreak:
    def test_volumeBreakoutEntry(self):
        # 横盘 30 天 → 放量突破前高 → 入场
        closes = [10.0] * 29 + [11.0]  # 第 30 天突破前 29 日高点
        bars = makeBars(closes)
        bars.loc[bars.index[-1], "high"] = 10.2
        bars.loc[bars.index[-1], "volume"] = 3_000_000.0  # 3 倍量
        strategy = getStrategy("s2_volume_break", breakWindow=20, volRatioMin=1.5, volMaMultiple=1.5)
        signals = strategy.generateSignals(bars)
        assert signals.iloc[-1] == 1

    def test_noVolumeNoEntry(self):
        # 突破但无量 → 不入场
        closes = [10.0] * 29 + [11.0]
        bars = makeBars(closes)  # conftest 恒定量
        strategy = getStrategy("s2_volume_break")
        signals = strategy.generateSignals(bars)
        assert signals.iloc[-1] == 0


class TestBatchAndOptimizeApi:
    @pytest.fixture(autouse=True)
    def _seedData(self, tmp_path, monkeypatch):
        # 把数据目录指到临时目录并写入两只标的
        import app.data.store as store
        import app.api.backtest as api

        monkeypatch.setattr(store, "DATA_DIR", tmp_path)
        monkeypatch.setattr(api, "loadBars", lambda m, s, period="day": store.loadBars(m, s, dataDir=tmp_path))
        saveBars(makeBars([10.0 + 0.1 * i for i in range(60)]), "cn", "300580", dataDir=tmp_path)
        saveBars(makeBars([10.0 + 0.1 * i for i in range(60)]), "cn", "300666", dataDir=tmp_path)

    def test_batchReturnsMetricsPerSymbol(self):
        resp = client.post(
            "/api/backtest/batch",
            json={
                "symbols": [{"market": "cn", "symbol": "300580"}, {"market": "cn", "symbol": "300666"}, {"market": "cn", "symbol": "000001"}],
                "strategy": "sma_cross",
                "params": {},
            },
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 3
        assert items[0]["metrics"]["totalReturn"] > 0  # 稳定上涨满仓盈利
        assert items[2]["error"] == "本地无数据"

    def test_optimizeSortedBySharpe(self):
        resp = client.post(
            "/api/backtest/optimize",
            json={
                "market": "cn",
                "symbol": "300580",
                "strategy": "sma_cross",
                "grid": {"fastWindow": [3, 5], "slowWindow": [10, 20]},
            },
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 4
        sharpes = [i["metrics"]["sharpeRatio"] for i in items]
        assert sharpes == sorted(sharpes, reverse=True)

    def test_optimizeGridTooLarge(self):
        resp = client.post(
            "/api/backtest/optimize",
            json={
                "market": "cn",
                "symbol": "300580",
                "strategy": "sma_cross",
                "grid": {"fastWindow": list(range(2, 30)), "slowWindow": list(range(5, 40))},
            },
        )
        assert resp.status_code == 400
