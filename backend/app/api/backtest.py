"""回测接口:策略列表与执行回测。"""
from fastapi import APIRouter, HTTPException

from app.backtest.engine import runBacktest
from app.backtest.strategies import getStrategy, listStrategies
from app.data.store import loadBars
from app.monitor.session import closedBars
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
    df = closedBars(df, req.market)
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


@router.post("/batch", response_model=list[BatchResultItem])
def batch(req: BatchBacktestRequest) -> list[BatchResultItem]:
    getStrategy(req.strategy, **req.params)
    items = []
    for item in req.symbols:
        try:
            df = loadBars(item.market, item.symbol)
            if df is None or df.empty:
                raise ValueError("本地无数据")
            result = runBacktest(closedBars(df, item.market), getStrategy(req.strategy, **req.params), req.feeRate)
            items.append(BatchResultItem(market=item.market, symbol=item.symbol, metrics=result["metrics"]))
        except (ValueError, OSError) as exc:
            items.append(BatchResultItem(market=item.market, symbol=item.symbol, error=str(exc)))
    return items


@router.post("/optimize", response_model=list[OptimizeResultItem])
def optimize(req: OptimizeRequest) -> list[OptimizeResultItem]:
    from itertools import product
    from math import prod

    strategy = getStrategy(req.strategy)
    if not req.grid or any(not values for values in req.grid.values()):
        raise HTTPException(status_code=400, detail="参数网格不能为空")
    if req.grid.keys() - strategy.paramsSchema.keys():
        raise HTTPException(status_code=422, detail="网格包含未知参数")
    if prod(len(values) for values in req.grid.values()) > 200:
        raise HTTPException(status_code=400, detail="参数组合不能超过200组")
    df = loadBars(req.market, req.symbol)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="本地无数据")
    results = []
    for values in product(*req.grid.values()):
        params = dict(zip(req.grid, values))
        try:
            result = runBacktest(closedBars(df, req.market), getStrategy(req.strategy, **params), req.feeRate)
        except ValueError:
            continue  # 快慢线等交叉约束可能排除部分组合。
        results.append(OptimizeResultItem(params=params, metrics=result["metrics"]))
    if not results:
        raise HTTPException(status_code=422, detail="没有满足参数约束的组合")
    return sorted(results, key=lambda item: item.metrics.sharpeRatio, reverse=True)
