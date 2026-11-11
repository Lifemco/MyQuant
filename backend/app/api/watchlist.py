"""自选股接口:增删改查,添加时自动抓取行情并补全名称。"""
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException

from app.api.data import _buildProvider
from app.data.store import loadBars, saveBars
from app.monitor.session import marketNow
from app.schemas.monitor import WatchItemIn, WatchItemOut, WatchItemUpdate
from app.watchlist.store import (
    addWatchItem,
    loadWatchlist,
    removeWatchItem,
    updateWatchItem,
)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


def _ensureBars(market: str, symbol: str) -> None:
    """本地无数据时自动抓取最近约 640 根日线。"""
    if loadBars(market, symbol) is not None:
        return
    end = marketNow(market).date()
    start = end - timedelta(days=365 * 3)
    try:
        df = _buildProvider(market).fetchDailyBars(
            symbol, start.isoformat(), end.isoformat()
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"行情抓取失败: {exc}") from exc
    if df.empty:
        raise HTTPException(status_code=404, detail=f"未获取到 {symbol} 的行情,请检查代码")
    saveBars(df, market, symbol, adjusted=True)


def _fetchName(market: str, symbol: str) -> str:
    """尽力补全股票名称,失败则返回代码本身。"""
    try:
        provider = _buildProvider(market, operation="quotes")
        fetchName = getattr(provider, "fetchName", None)
        if callable(fetchName):
            return fetchName(symbol) or symbol
    except Exception:
        pass
    return symbol


@router.get("", response_model=list[WatchItemOut])
def listItems() -> list[WatchItemOut]:
    return [WatchItemOut(**item) for item in loadWatchlist()]


@router.post("", response_model=WatchItemOut, status_code=201)
def addItem(req: WatchItemIn) -> WatchItemOut:
    symbol = req.symbol.strip()
    _ensureBars(req.market, symbol)
    item = addWatchItem(req.market, symbol, name=_fetchName(req.market, symbol))
    return WatchItemOut(**item)


@router.put("/{market}/{symbol}", response_model=WatchItemOut)
def updateItem(market: str, symbol: str, req: WatchItemUpdate) -> WatchItemOut:
    item = updateWatchItem(market, symbol, req.strategy, req.params)
    if item is None:
        raise HTTPException(status_code=404, detail=f"自选股不存在: {market}/{symbol}")
    return WatchItemOut(**item)


@router.delete("/{market}/{symbol}", status_code=204)
def deleteItem(market: str, symbol: str) -> None:
    if not removeWatchItem(market, symbol):
        raise HTTPException(status_code=404, detail=f"自选股不存在: {market}/{symbol}")
