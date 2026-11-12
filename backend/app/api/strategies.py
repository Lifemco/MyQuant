from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.backtest.engine import runBacktest
from app.data import third_party
from app.data.store import loadBars
from app.data.contract import validateBars
from app.monitor.service import computeSignalMarkers
from app.monitor.session import closedBars
from app.strategies import store
from app.strategies.models import AgentDraft, DraftRequest, ExecuteStrategy, FactorUpload, SaveStrategy, StrategySpec
from app.strategies.runtime import FixedSignals, RuleStrategy

router = APIRouter(prefix="/api/strategies", tags=["strategy-studio"])


@router.get("/capabilities")
def capabilities():
    return {**third_party.agentStatus(), "schema": StrategySpec.model_json_schema(), "factors": store.listFactors(),
            "execution": "每只标的独立做多/空仓回测与最新收盘信号；非组合调仓或实盘下单"}


@router.post("/draft")
def draft(request: DraftRequest):
    if not third_party.agentStatus()["configured"]:
        raise HTTPException(503, "请在后端配置LLM_BASE_URL、LLM_MODEL、LLM_API_KEY")
    try:
        result = AgentDraft.model_validate(third_party.strategyAgentRequest(request.prompt, AgentDraft.model_json_schema(), store.listFactors()))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(502, "模型未返回符合策略规则的JSON，请补充描述后重试") from exc
    except Exception as exc:
        raise HTTPException(502, "策略模型服务连接失败，请检查后端模型配置和网络") from exc
    return {**result.model_dump(), "ready": result.spec is not None and not result.questions and not result.unsupported}


@router.get("/library")
def library():
    return store.listSaved()


@router.post("/validate")
def validate(request: StrategySpec):
    return request.model_dump()


@router.post("/library")
def save(request: SaveStrategy):
    try:
        return store.saveStrategy(request)
    except store.VersionConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/factors")
def factors():
    return store.listFactors()


@router.post("/factors")
def upload(request: FactorUpload):
    return store.saveFactor(request)


@router.post("/execute")
def execute(request: ExecuteStrategy):
    results = []
    for item in request.symbols:
        try:
            frame = loadBars(item.market, item.symbol)
            if frame is None or frame.empty:
                raise ValueError("缺少缓存行情，请先下载或刷新")
            frame = closedBars(validateBars(frame), item.market)
            strategy = RuleStrategy(request.spec, item.market, item.symbol)
            frozen = FixedSignals(strategy.generateSignals(frame))
            result = runBacktest(frame, frozen, request.feeRate)
            signals = computeSignalMarkers(frame, frozen)
            results.append({"market": item.market, "symbol": item.symbol, **result, **signals,
                            "dataAsOf": frame.date.iloc[-1].date().isoformat(), "dataInfo": frame.attrs.get("marketData"), "factors": strategy.factorSources})
        except (ValueError, OSError) as exc:
            results.append({"market": item.market, "symbol": item.symbol, "error": str(exc)})
    return {"spec": request.spec.model_dump(), "execution": "T日收盘决策，下一交易日开盘执行；每只标的独立回测", "results": results}
