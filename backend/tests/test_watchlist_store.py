"""自选股存储单元测试(临时目录隔离)。"""
from app.watchlist.store import (
    addWatchItem,
    getWatchItem,
    loadWatchlist,
    removeWatchItem,
    updateWatchItem,
)


def test_addAndLoad(tmp_path):
    item = addWatchItem("cn", "600519", "贵州茅台", dataDir=tmp_path)
    assert item["strategy"] == "sma_cross"  # 默认策略
    items = loadWatchlist(dataDir=tmp_path)
    assert len(items) == 1 and items[0]["name"] == "贵州茅台"


def test_addDuplicateReturnsExisting(tmp_path):
    addWatchItem("cn", "600519", "贵州茅台", dataDir=tmp_path)
    again = addWatchItem("cn", "600519", "改名", dataDir=tmp_path)
    assert again["name"] == "贵州茅台"  # 不覆盖
    assert len(loadWatchlist(dataDir=tmp_path)) == 1


def test_updateStrategyAndParams(tmp_path):
    addWatchItem("cn", "600519", dataDir=tmp_path)
    updated = updateWatchItem(
        "cn", "600519", "rsi_reversion", {"window": 14}, dataDir=tmp_path
    )
    assert updated is not None and updated["strategy"] == "rsi_reversion"
    assert getWatchItem("cn", "600519", dataDir=tmp_path)["params"] == {"window": 14, "oversold": 30.0, "overbought": 70.0}


def test_updateMissingReturnsNone(tmp_path):
    assert updateWatchItem("cn", "000001", "sma_cross", {}, dataDir=tmp_path) is None


def test_remove(tmp_path):
    addWatchItem("us", "AAPL", dataDir=tmp_path)
    assert removeWatchItem("us", "AAPL", dataDir=tmp_path) is True
    assert removeWatchItem("us", "AAPL", dataDir=tmp_path) is False
    assert loadWatchlist(dataDir=tmp_path) == []
