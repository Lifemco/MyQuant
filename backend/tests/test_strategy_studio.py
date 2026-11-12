"""策略DSL、时点因子、Agent边界与持久化。测试不访问真实模型服务。"""
import json
from datetime import datetime, timezone

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import strategies as api
from app.backtest.engine import runBacktest
from app.data import third_party
from app.main import app
from app.strategies import store
from app.strategies.models import AgentDraft, FactorUpload, StrategySpec
from app.strategies.runtime import RuleStrategy, alignFactor
from tests.conftest import makeBars


def operand(kind, **kwargs):
    return {"kind": kind, **kwargs}


def condition(left, op, right):
    return {"left": left, "op": op, "right": right}


def spec(**kwargs):
    return StrategySpec.model_validate({"name": "测试策略", "entry": {"logic": "all", "conditions": [condition(operand("close"), "gt", operand("constant", value=10))]},
          "exit": {"logic": "any", "conditions": [condition(operand("close"), "lt", operand("constant", value=5))]}, **kwargs})


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "STRATEGY_DIR", tmp_path)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    return TestClient(app)


def test_rules_next_open_and_close_risk_uses_execution_price():
    bars = makeBars([11, 19, 19, 11], "2024-01-01")
    bars["open"] = [10, 20, 18, 10]
    strategy = RuleStrategy(spec(stopLossPct=.05), "cn", "600519")
    # 第一天11触发，次日20开盘入场、19收盘触发5%止损，第三日18开盘退出。
    signals = strategy.generateSignals(bars)
    assert signals.tolist()[:3] == [1, 0, 1]
    result = runBacktest(bars, strategy, 0)
    assert result["trades"][0]["entryPrice"] == 20
    assert result["trades"][0]["exitPrice"] == 18
    assert result["trades"][0]["pnlPct"] == -.1


def test_exit_precedence_crossing_warmup_and_no_future():
    rules = spec(entry={"logic": "all", "conditions": [condition(operand("sma", window=2), "cross_above", operand("sma", window=3))]},
                 exit={"logic": "any", "conditions": [condition(operand("sma", window=2), "cross_below", operand("sma", window=3))]})
    first = makeBars([5, 4, 3, 4, 6, 8], "2024-01-01")
    extended = makeBars([5, 4, 3, 4, 6, 8, 1, 2], "2024-01-01")
    a = RuleStrategy(rules, "cn", "600519").generateSignals(first)
    b = RuleStrategy(rules, "cn", "600519").generateSignals(extended)
    assert a.tolist() == b.iloc[:len(a)].tolist()
    assert a.iloc[:4].sum() == 0 and a.iloc[4] == 1
    both = spec(exit={"logic": "any", "conditions": [condition(operand("close"), "gt", operand("constant", value=0))]})
    assert RuleStrategy(both, "cn", "600519").generateSignals(first).sum() == 0


def test_maximum_holding_period_and_take_profit():
    bars = makeBars([11, 12, 15, 18], "2024-01-01")
    bars["open"] = [10, 11, 12, 15]
    holding = RuleStrategy(spec(maxHoldingBars=1), "cn", "600519").generateSignals(bars)
    assert holding.tolist() == [1, 0, 1, 0]
    profit = RuleStrategy(spec(takeProfitPct=.2), "cn", "600519").generateSignals(bars)
    assert profit.tolist() == [1, 1, 0, 1]


@pytest.mark.parametrize("market,published", [("cn", "2024-01-02T15:01:00+08:00"), ("us", "2024-07-02T16:01:00-04:00")])
def test_factor_after_close_available_next_session_and_expiry(market, published):
    day = pd.Timestamp(published).date().isoformat()
    dates = pd.Series(pd.date_range(day, periods=4))
    rows = pd.DataFrame({"availableAt": [published], "value": [18.0]})
    aligned = alignFactor(rows, dates, market, 2)
    assert pd.isna(aligned.iloc[0])
    assert aligned.iloc[1] == 18
    assert pd.isna(aligned.iloc[-1])


def test_factor_upload_validation_source_persistence_and_missing_data(client):
    body = {"market": "cn", "symbol": "600519", "factor": "pe_ttm", "source": "测试财报实际披露", "observations": [{"availableAt": "2024-01-02T18:00:00+08:00", "value": 18}]}
    response = client.post("/api/strategies/factors", json=body)
    assert response.status_code == 200
    assert store.loadFactor("cn", "600519", "pe_ttm").attrs["source"] == body["source"]
    assert client.get("/api/strategies/factors").json()[0]["rows"] == 1
    body["observations"][0]["availableAt"] = "2024-01-02"
    assert client.post("/api/strategies/factors", json=body).status_code == 422
    body["factor"] = "../file"
    assert client.post("/api/strategies/factors", json=body).status_code == 422
    with pytest.raises(ValueError, match="缺少外部因子"):
        store.loadFactor("cn", "600519", "missing")


def test_factor_duplicate_rejected_without_overwriting(client):
    body = {"market": "cn", "symbol": "600519", "factor": "sentiment", "source": "测试", "observations": [{"availableAt": "2024-01-02T10:00:00+08:00", "value": .5}]}
    assert client.post("/api/strategies/factors", json=body).status_code == 200
    body["observations"] *= 2
    assert client.post("/api/strategies/factors", json=body).status_code == 422
    assert len(store.loadFactor("cn", "600519", "sentiment")) == 1


def test_library_versions_and_validate_unknown_code(client):
    body = {"spec": spec().model_dump(), "prompt": "我的策略"}
    item = client.post("/api/strategies/library", json=body).json()
    assert item["version"] == 1
    assert client.get("/api/strategies/library").json()[0]["id"] == item["id"]
    body.update(id=item["id"], version=1)
    assert client.post("/api/strategies/library", json=body).json()["version"] == 2
    assert client.post("/api/strategies/library", json=body).status_code == 409
    body["spec"]["code"] = "__import__('os').system('false')"
    assert client.post("/api/strategies/validate", json=body["spec"]).status_code == 422


def test_agent_not_configured_and_draft_validation(client, monkeypatch):
    assert not client.get("/api/strategies/capabilities").json()["configured"]
    assert client.post("/api/strategies/draft", json={"prompt": "写一个策略"}).status_code == 503
    monkeypatch.setattr(third_party, "agentStatus", lambda: {"configured": True, "model": "test"})
    answer = {"summary": "测试整理", "spec": spec().model_dump(), "questions": [], "unsupported": []}
    monkeypatch.setattr(third_party, "strategyAgentRequest", lambda *args: answer)
    assert client.post("/api/strategies/draft", json={"prompt": "收盘价高于10买入，小于5卖出"}).json()["ready"]
    answer["questions"] = ["需要明确仓位"]
    assert not client.post("/api/strategies/draft", json={"prompt": "买点不清楚"}).json()["ready"]
    answer["questions"] = []
    answer["unsupported"] = ["实盘下单"]
    assert not client.post("/api/strategies/draft", json={"prompt": "实盘下单"}).json()["ready"]
    answer["spec"]["entry"]["conditions"][0]["left"]["kind"] = "python_eval"
    assert client.post("/api/strategies/draft", json={"prompt": "任意代码"}).status_code == 502


def test_execute_isolated_symbols_and_single_factor_snapshot(client, monkeypatch):
    from app.strategies import runtime
    calls = []
    original = runtime.loadFactor
    def read(*args):
        calls.append(args)
        return original(*args)
    monkeypatch.setattr(runtime, "loadFactor", read)
    store.saveFactor(FactorUpload.model_validate({"market": "cn", "symbol": "600519", "factor": "event_score", "source": "事件发布记录", "observations": [{"availableAt": "2023-12-29T10:00:00+08:00", "value": 1}]}))
    rules = spec(entry={"conditions": [condition(operand("external", factor="event_score"), "gt", operand("constant", value=0))]})
    monkeypatch.setattr(api, "loadBars", lambda market,symbol: makeBars([10,11,12,13], "2024-01-01") if symbol == "600519" else None)
    response = client.post("/api/strategies/execute", json={"spec": rules.model_dump(), "symbols": [{"market": "cn", "symbol": "600519"}, {"market": "cn", "symbol": "000001"}]})
    assert response.status_code == 200
    rows = response.json()["results"]
    assert rows[0]["holding"] and rows[0]["metrics"]["totalTrades"] == 1
    assert rows[0]["factors"]["event_score"]["source"] == "事件发布记录"
    assert "缺少缓存" in rows[1]["error"]
    assert len(calls) == 1


def test_model_gateway_uses_configured_endpoint_and_bounded_json(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://model.example/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "test-only-key")
    original = httpx.Client
    seen = []
    answer = AgentDraft(summary="测试", spec=spec()).model_dump()
    def handle(request):
        seen.append(request)
        return httpx.Response(200,json={"choices": [{"message": {"content": json.dumps(answer)}}]})
    monkeypatch.setattr(third_party.httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    value = third_party.strategyAgentRequest("测试自然语言", AgentDraft.model_json_schema(), [])
    assert value["summary"] == "测试"
    assert str(seen[0].url) == "https://model.example/v1/chat/completions"
    payload = json.loads(seen[0].content)
    assert payload["model"] == "test-model" and len(payload["messages"]) == 2
    assert "不生成Python" in payload["messages"][0]["content"]
    assert "test-only-key" not in str(third_party.agentStatus())
    monkeypatch.setitem(third_party.AGENT_SETTINGS, "maxResponseBytes", 10)
    with pytest.raises(ValueError, match="过大"):
        third_party.strategyAgentRequest("测试自然语言", AgentDraft.model_json_schema(), [])


def test_health_probes_and_volume_failure(client, monkeypatch, tmp_path):
    import app.main as main
    assert client.get("/api/health/live").status_code == 200
    monkeypatch.setattr(main, "DATA_DIR", tmp_path / "data")
    assert client.get("/api/health/ready").status_code == 200
    def fail(**kwargs): raise PermissionError()
    monkeypatch.setattr(main.tempfile, "TemporaryFile", fail)
    assert client.get("/api/health/ready").status_code == 503


@pytest.mark.parametrize("value", [True, float("nan"), float("inf")])
def test_invalid_numeric_factor_returns_validation_error(client, value):
    body = {"market": "cn", "symbol": "600519", "factor": "event_score", "source": "private-input-must-not-be-echoed",
            "observations": [{"availableAt": "2024-01-02T10:00:00+08:00", "value": value}]}
    response = client.post("/api/strategies/factors", content=json.dumps(body), headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert "private-input" not in response.text


def test_execution_normalizes_date_order_and_rejects_corrupt_prices(client, monkeypatch):
    bars = makeBars([9,11,12,13], "2024-01-01")
    monkeypatch.setattr(api, "loadBars", lambda *args: bars.iloc[::-1].copy())
    payload = {"spec": spec().model_dump(), "symbols": [{"market": "cn", "symbol": "600519"}]}
    item = client.post("/api/strategies/execute", json=payload).json()["results"][0]
    assert item["trades"][0]["entryDate"] == "2024-01-03"
    assert item["dataAsOf"] == "2024-01-04"
    bars.loc[1, "open"] = 0
    item = client.post("/api/strategies/execute", json=payload).json()["results"][0]
    assert item["error"] and "metrics" not in item
