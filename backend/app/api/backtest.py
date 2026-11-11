"""回测接口:策略列表与执行回测。"""
from fastapi import APIRouter, HTTPException

from app.backtest.engine import runBacktest
from app.backtest.strategies import getStrategy, listStrategies
from app.data.store import loadBars
from app.schemas.api import (
    BatchBacktestRequest,
    BatchResultItem,
    OptimizeRequest,
    OptimizeResultItem,
    RunBacktestRequest,
    RunBacktestResponse,
    StrategyMeta,
)

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


@router.get("/strategies", response_model=list[StrategyMeta])
def getStrategies() -> list[StrategyMeta]:
    """返回全部可用策略及参数说明。"""
    return [StrategyMeta(**item) for item in listStrategies()]


@router.post("/run", response_model=RunBacktestResponse)
def run(req: RunBacktestRequest) -> RunBacktestResponse:
    """对本地缓存数据执行回测,返回净值曲线、指标、交易明细与K线。"""
    df = loadBars(req.market, req.symbol)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"本地无 {req.market}/{req.symbol} 数据,请先抓取")
    try:
        strategy = getStrategy(req.strategy, **req.params)
        result = runBacktest(df, strategy, feeRate=req.feeRate)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return RunBacktestResponse(
        metrics=result["metrics"],
        equityCurve=result["equityCurve"],
        trades=result["trades"],
        bars=[
            {
                "date": str(row.date.date()),
                "open": round(float(row.open), 4),
                "high": round(float(row.high), 4),
                "low": round(float(row.low), 4),
                "close": round(float(row.close), 4),
                "volume": float(row.volume),
            }
            for row in df.itertuples()
        ],
    )
