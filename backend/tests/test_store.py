"""本地存储单元测试(使用临时目录隔离)。"""
from app.data.store import listSymbols, loadBars, saveBars
from tests.conftest import makeBars


def test_saveAndLoadRoundTrip(tmp_path):
    bars = makeBars([100.0, 101.0, 102.0])
    saveBars(bars, "cn", "600519", dataDir=tmp_path)
    loaded = loadBars("cn", "600519", dataDir=tmp_path)
    assert loaded is not None and len(loaded) == 3
    assert list(loaded["close"]) == [100.0, 101.0, 102.0]


def test_saveMergesAndDeduplicates(tmp_path):
    # 同一日期重复写入时保留新值
    old = makeBars([100.0, 101.0], start="2024-01-01")
    new = makeBars([999.0, 102.0], start="2024-01-02")
    saveBars(old, "us", "AAPL", dataDir=tmp_path)
    saveBars(new, "us", "AAPL", dataDir=tmp_path)
    loaded = loadBars("us", "AAPL", dataDir=tmp_path)
    assert len(loaded) == 3
    assert loaded.iloc[1]["close"] == 999.0


def test_loadMissingReturnsNone(tmp_path):
    assert loadBars("cn", "000001", dataDir=tmp_path) is None


def test_listSymbols(tmp_path):
    saveBars(makeBars([1.0, 2.0]), "cn", "600519", dataDir=tmp_path)
    saveBars(makeBars([1.0, 2.0, 3.0]), "us", "AAPL", dataDir=tmp_path)
    symbols = listSymbols(dataDir=tmp_path)
    assert len(symbols) == 2
    assert {s["market"] for s in symbols} == {"cn", "us"}
    assert all(s["rows"] >= 2 for s in symbols)
