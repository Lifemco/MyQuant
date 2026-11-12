"""市场总览统计及采集边界：使用明确的合成数据，不将其作为实盘验收。"""
from datetime import datetime
from threading import Event
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.data import third_party
from app.main import app
from app.market import service
from tests.conftest import makeBars


@pytest.fixture
def market(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "MARKET_DIR", tmp_path)
    return tmp_path


def test_distribution_boundaries_and_explicit_exclusions():
    changes = [-11, -10, -7, -5, -3, -1, 0, 1, 3, 5, 7, 10, 11, np.nan, 1]
    frame = pd.DataFrame({"symbol": [f"{i:06}" for i in range(len(changes))], "change": changes, "close": 10, "amount": [100] * 14 + [0]})
    data = service.distribution(frame)
    assert [b["count"] for b in data["bins"]] == [1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 2]
    assert data["valid"] == 13 and data["excluded"] == 2
    assert data["up"] + data["down"] + data["flat"] == 13
    with pytest.raises(ValueError, match="重复"):
        service.distribution(pd.concat([frame, frame.iloc[:1]]))


def test_style_uses_common_base_and_dates():
    a = pd.DataFrame({"date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]), "close": [10, 20, 30]})
    b = pd.DataFrame({"date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]), "close": [100, 80, 70]})
    data = service.relativePerformance({"a": a, "b": b})
    assert data["baseDate"] == "2024-01-02"
    assert data["dates"] == ["2024-01-02", "2024-01-03"]
    assert data["series"][0]["values"] == [100, 150]
    assert data["series"][1]["values"] == [100, 80]


def test_valuation_trailing_window_ties_and_no_lookahead():
    frame = pd.DataFrame({"date": ["2014-01-01", "2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04"], "pe": [1, 10, 10, 20, -1]})
    data = service.valuation(frame)["points"]
    assert data[1]["samples"] == 1  # 2014不在2020的五年窗口。
    assert data[1]["percentile"] == 50  # 未来20倍PE不参与当日排序。
    assert data[2]["percentile"] == 50  # 并列值中位秩。
    assert data[-1]["percentile"] == pytest.approx(5 / 6 * 100)
    assert data[-1]["date"] == "2020-01-03"


def test_breadth_separate_denominators_halts_and_equality():
    long = makeBars(list(range(1, 66)), "2024-01-01")
    short = makeBars([10] * 30, "2024-02-19")
    halted = makeBars([10] * 65, "2024-01-01")
    halted["volume"] = 0
    data = service.breadth({"long": long, "short": short, "halted": halted}, 5)
    row = next(p for p in data["points"] if p["date"] == "2024-03-29")
    assert row["eligible20"] == 2 and row["eligible60"] == 1
    assert row["ma20"] == 50 and row["ma60"] == 100
    assert data["total"] == 5 and data["collected"] == 3


def test_index_excludes_intraday_and_rejects_bad_amount(monkeypatch):
    monkeypatch.setattr("app.monitor.session.marketNow", lambda _: datetime(2024, 1, 3, 10, tzinfo=service.CN))
    frame = pd.DataFrame({"date": ["2024-01-02", "2024-01-03"], "close": [100, 101], "amount": [1e9, 2e9]})
    assert len(service.indexHistory(frame)) == 1
    frame.loc[0, "amount"] = -1
    with pytest.raises(ValueError, match="无效"):
        service.indexHistory(frame)


def test_gateway_configuration_and_timeout_restoration(monkeypatch):
    seen = {}
    def sdkCall(**params):
        seen.update(params)
        return pd.DataFrame({"日期": ["2024-01-02"], "收盘": [100], "成交额": [1e8]})
    fake = SimpleNamespace(get_timeout=lambda: 7, set_timeout=lambda v: seen.setdefault("timeouts", []).append(v), custom=sdkCall)
    monkeypatch.setattr(third_party.importlib, "import_module", lambda _: fake)
    monkeypatch.setitem(third_party.MARKET_OVERVIEW["calls"]["index"], "method", "custom")
    frame = third_party.marketOverviewRequest("index", symbol="000300", startDate="2024-01-01", endDate="2024-01-02")
    assert list(frame.columns) == ["date", "close", "amount"]
    assert seen == {"timeouts": [15, 7], "period": "daily", "symbol": "000300", "start_date": "20240101", "end_date": "20240102"}
    def fail(**_):
        raise ConnectionError("failure")
    fake.custom = fail
    with pytest.raises(ConnectionError):
        third_party.marketOverviewRequest("index", symbol="000300")
    assert seen["timeouts"][-1] == 7


def fakeRequest(operation, **_):
    if operation == "index":
        return pd.DataFrame({"date": ["2024-01-02", "2024-01-03"], "close": [100, 110], "amount": [1e8, 2e8]})
    if operation == "spot":
        return pd.DataFrame({"symbol": ["600519", "000001", "830001"], "change": [1, -1, 0], "close": [10, 20, 30], "amount": [100, 200, 0]})
    if operation == "industry":
        return pd.DataFrame({"symbol": ["BK001"], "name": ["测试行业"], "change": [1.2], "size": [1e11]})
    return pd.DataFrame({"date": ["2024-01-02", "2024-01-03"], "pe": [10, 11]})


def test_refresh_all_sections_independent_cache_and_failure_retention(market, monkeypatch):
    monkeypatch.setattr(third_party, "marketOverviewRequest", fakeRequest)
    service._refresh()
    content = service.overview()
    assert set(content["sections"]) == set(service.SECTION_NAMES)
    assert all(section["data"] is not None for key, section in content["sections"].items() if key != "breadth")
    assert content["sections"]["distribution"]["asOf"] is None
    assert content["sections"]["distribution"]["data"]["total"] == 3
    assert len(pd.read_parquet(market / "universe.parquet")) == 3
    assert not (market / "watchlist.json").exists()
    before = content["sections"]["trend"]["data"]
    def fail(*_, **__):
        raise ConnectionError("https://secret.invalid/?token=PRIVATE")
    monkeypatch.setattr(third_party, "marketOverviewRequest", fail)
    service._refresh()
    content = service.overview()
    assert content["sections"]["trend"]["status"] == "stale"
    assert content["sections"]["trend"]["data"] == before
    assert "PRIVATE" not in str(content)


def test_api_empty_read_never_fetches_and_breadth_requires_universe(market, monkeypatch):
    monkeypatch.setattr(third_party, "marketOverviewRequest", lambda *_: pytest.fail("GET不应触发采集"))
    client = TestClient(app)
    response = client.get("/api/market/overview")
    assert response.status_code == 200
    assert len(response.json()["sections"]) == 6
    assert all(v["status"] == "unavailable" for v in response.json()["sections"].values())
    assert client.post("/api/market/breadth").status_code == 422


def test_collection_single_flight_and_restart_detection(market, monkeypatch):
    entered, release, finished = Event(), Event(), Event()
    def collect():
        entered.set()
        release.wait(5)
    monkeypatch.setattr(service, "_refresh", collect)
    original = service._run
    def run(*args):
        try:
            original(*args)
        finally:
            finished.set()
    monkeypatch.setattr(service, "_run", run)
    try:
        assert service.startCollection()["job"]["running"]
        assert entered.wait(2)
        assert service.startCollection()["job"]["running"]
    finally:
        release.set()
        assert finished.wait(2)
    assert not service.overview()["job"]["running"]
    service._write(job={"running": True, "kind": "refresh"})
    assert "已停止" in service.overview()["job"]["error"]


def test_breadth_collect_cache_resume_and_explicit_scope(market, monkeypatch):
    universe = pd.DataFrame({"symbol": ["600519", "000001", "830001"]})
    universe.attrs["observedAt"] = service.now().isoformat()
    universe.to_parquet(market / "universe.parquet")
    calls = []
    class Provider:
        def fetchDailyBars(self, symbol, *_, **__):
            calls.append(symbol)
            return makeBars(list(range(1, 66)), "2024-01-01")
    monkeypatch.setattr(third_party, "makeProvider", lambda *args: Provider())
    service._collectBreadth()
    data = service._read()["sections"]["breadth"]["data"]
    assert calls == ["600519", "000001"]
    assert data["total"] == data["collected"] == 2
    service._collectBreadth()
    assert len(calls) == 2  # 同一目标日复用完整窗口；不与自选股缓存混合。
    monkeypatch.setitem(third_party.MARKET_OVERVIEW["breadth"], "adjustment", "hfq")
    service._collectBreadth()
    assert len(calls) == 4  # 修改统一配置后不复用旧复权口径。


def test_breadth_fail_fast_and_preserve_cache(market, monkeypatch):
    universe = pd.DataFrame({"symbol": [f"600{i:03}" for i in range(20)]})
    universe.attrs["observedAt"] = service.now().isoformat()
    universe.to_parquet(market / "universe.parquet")
    calls = []
    class Provider:
        def fetchDailyBars(self, symbol, *_, **__):
            calls.append(symbol)
            raise ConnectionError()
    monkeypatch.setattr(third_party, "makeProvider", lambda *args: Provider())
    with pytest.raises(RuntimeError, match="连续5"):
        service._collectBreadth()
    assert len(calls) == 5
    assert service._read()["job"]["done"] == 5


def test_expired_snapshot_not_presented_as_fresh(market):
    service._section("industry", [{"name": "cached"}], "source", "notes")
    content = service._read()["sections"]["industry"]
    content["fetchedAt"] = "2020-01-01T00:00:00+08:00"
    service._write(section=("industry", content))
    assert service.overview()["sections"]["industry"]["status"] == "stale"


def test_breadth_rejects_expired_universe(market):
    universe = pd.DataFrame({"symbol": ["600519"]})
    universe.attrs["observedAt"] = "2020-01-01T00:00:00+08:00"
    universe.to_parquet(market / "universe.parquet")
    with pytest.raises(ValueError, match="已过期"):
        service.startCollection("breadth")


@pytest.mark.parametrize("success", [True, False])
def test_valuation_process_cleanup_on_success_and_timeout(monkeypatch, success):
    events = []
    class Process:
        pid = 1
        def start(self): events.append("start")
        def is_alive(self): return "terminate" not in events
        def terminate(self): events.append("terminate")
        def join(self, timeout=None): events.append("join")
    payload = pd.DataFrame({"date": ["2024-01-02"], "pe": [12]})
    receiver = SimpleNamespace(poll=lambda timeout: success, recv=lambda: (True, payload), close=lambda: None)
    sender = SimpleNamespace(close=lambda: None)
    context = SimpleNamespace(Pipe=lambda **kw: (receiver, sender), Process=lambda **kw: Process())
    monkeypatch.setattr(third_party.multiprocessing, "get_context", lambda kind: context)
    if success:
        assert third_party.marketOverviewRequest("valuation").equals(payload)
    else:
        with pytest.raises(TimeoutError):
            third_party.marketOverviewRequest("valuation")
    assert events == ["start", "terminate", "join"]


@pytest.mark.parametrize("mode", ["success", "error", "hang"])
def test_valuation_real_process_without_network(monkeypatch, tmp_path, mode):
    """实际spawn/IPC/回收验证；本地SDK替身不访问任何行情域名。"""
    (tmp_path / "market_fixture_sdk.py").write_text('''
import pandas as pd
import time
def get_timeout(): return 7
def set_timeout(value): pass
def custom(symbol):
    if symbol == "hang": time.sleep(60)
    if symbol == "error": raise RuntimeError("private-token-must-not-leak")
    return pd.DataFrame({"日期": ["2024-01-02"], "滚动市盈率": [12.3]})
''')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setitem(third_party.MARKET_OVERVIEW, "sdk", "market_fixture_sdk")
    call = third_party.MARKET_OVERVIEW["calls"]["valuation"]
    monkeypatch.setitem(call, "method", "custom")
    monkeypatch.setitem(call, "params", {"symbol": mode})
    monkeypatch.setitem(call, "requestTimeout", 0.15 if mode == "hang" else 15)
    if mode == "success":
        assert third_party.marketOverviewRequest("valuation").pe.tolist() == [12.3]
    elif mode == "hang":
        with pytest.raises(TimeoutError):
            third_party.marketOverviewRequest("valuation")
    else:
        with pytest.raises(RuntimeError) as error:
            third_party.marketOverviewRequest("valuation")
        assert "private-token" not in str(error.value)
