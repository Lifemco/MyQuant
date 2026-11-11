"""监控接口:自选列表的信号总览、单票K线+买卖点、批量行情刷新。"""
from datetime import date, datetime, timedelta

import pandas as pd
from fastapi import APIRouter, HTTPException

from app.api.data import _buildProvider
from app.backtest.strategies import getStrategy
from app.data.store import loadBars, saveBars
from app.monitor.service import computeSignalMarkers, summarizeBars
from app.monitor.session import closedBars, marketNow, ZONES
from app.data.contract import META_KEY, describeBars, instrument
from zoneinfo import ZoneInfo
from app.schemas.monitor import (
    ChartRequest,
    ChartResponse,
    MinuteResponse,
    QuoteRequest,
    QuoteSnapshot,
    SignalMarker,
    WatchOverviewItem,
)
from app.watchlist.store import loadWatchlist

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


def _overviewFor(item: dict) -> WatchOverviewItem:
    """对单只自选计算信号总览;数据缺失时降级为无信号状态。"""
    bars = loadBars(item["market"], item["symbol"])
    base = {**item, "holding": False, "lastSignal": None, "close": None, "changePct": None}
    confirmed = closedBars(bars, item["market"]) if bars is not None else None
    if bars is not None and not bars.empty:
        base["dataAsOf"] = str(bars["date"].max().date())
        base["dataInfo"] = bars.attrs.get(META_KEY)
        base["error"] = bars.attrs.get("historyNotice") or (None if base["dataInfo"] else "旧缓存来源、复权和单位未确认；请刷新后核对")
    if confirmed is not None and not confirmed.empty:
        base["signalAsOf"] = str(confirmed["date"].max().date())
    if bars is None or bars.empty:
        return WatchOverviewItem(**base)
    try:
        strategy = getStrategy(item["strategy"], **item.get("params", {}))
        signals = computeSignalMarkers(confirmed, strategy)
    except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
        base["error"] = f"策略计算失败: {exc}"
        return WatchOverviewItem(**base)
    summary = summarizeBars(bars)
    # base 已含默认状态,此处只覆盖计算结果,避免关键字重复
    return WatchOverviewItem(
        **{
            **base,
            "holding": signals["holding"],
            "lastSignal": signals["lastSignal"],
            "close": summary["close"],
            "changePct": summary["changePct"],
        }
    )


@router.get("/overview", response_model=list[WatchOverviewItem])
def overview() -> list[WatchOverviewItem]:
    """全部自选股的信号与行情摘要(读本地缓存,不触发抓取)。"""
    return [_overviewFor(item) for item in loadWatchlist()]


@router.post("/refresh", response_model=list[WatchOverviewItem])
def refresh() -> list[WatchOverviewItem]:
    """刷新全部自选股的最新行情(增量合并),再返回信号总览。"""
    results = []
    for item in loadWatchlist():
        errors = []
        # 已经打开过的周/月图也必须随手动刷新更新。
        for period in ("day", "week", "month"):
            if period != "day" and loadBars(item["market"], item["symbol"], period=period) is None:
                continue
            try:
                df = _fetchAndCache(item["market"], item["symbol"], period)
                if df is None or df.empty:
                    errors.append(f"{period}: 数据源返回空数据")
            except Exception as exc:
                errors.append(f"{period}: {getattr(exc, 'detail', str(exc))}")
        result = _overviewFor(item)
        result.refreshError = "; ".join(errors) or None
        result.refreshedAt = marketNow(item["market"]).isoformat() if not errors else None
        results.append(result)
    return results


@router.post("/chart", response_model=ChartResponse)
def chart(req: ChartRequest) -> ChartResponse:
    """单票K线 + 买卖点标记;策略参数来自请求,支持临时预览;支持日/周/月周期。"""
    bars = loadBars(req.market, req.symbol, period=req.period)
    if bars is None or bars.empty:
        # 周/月线首次访问时按需抓取并缓存
        bars = _fetchAndCache(req.market, req.symbol, req.period)
    if bars is None or bars.empty:
        raise HTTPException(status_code=404, detail=f"无 {req.market}/{req.symbol} 的 {req.period} 数据")
    # 日线:合并当日进行中的K线(腾讯日线接口盘中不含当日)
    if req.period == "day":
        bars = _mergeTodayBar(req.market, req.symbol, bars)
    try:
        strategy = getStrategy(req.strategy, **req.params)
        confirmed = closedBars(bars, req.market, req.period)
        signals = computeSignalMarkers(confirmed, strategy)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ChartResponse(
        dataInfo=bars.attrs.get(META_KEY),
        signalAsOf=str(confirmed["date"].max().date()) if not confirmed.empty else None,
        bars=[
            {
                "date": str(row.date.date()),
                "open": round(float(row.open), 4),
                "high": round(float(row.high), 4),
                "low": round(float(row.low), 4),
                "close": round(float(row.close), 4),
                "volume": float(row.volume),
            }
            for row in bars.itertuples()
        ],
        markers=[SignalMarker(**m) for m in signals["markers"]],
        holding=signals["holding"],
        lastSignal=SignalMarker(**signals["lastSignal"]) if signals["lastSignal"] else None,
    )


def _quoteTradeDate(timeStr: str) -> date | None:
    """从快照时间串解析交易日期:A股 '20260930100310',港股 '2026/09/30 09:48:04'。"""
    if len(timeStr) >= 8 and timeStr[:8].isdigit():
        return datetime.strptime(timeStr[:8], "%Y%m%d").date()
    if len(timeStr) >= 10 and "/" in timeStr[:10]:
        return datetime.strptime(timeStr[:10], "%Y/%m/%d").date()
    return None


def _mergeQuoteBar(bars: pd.DataFrame, quote: dict, today: date) -> pd.DataFrame:
    """把实时快照合成/更新为当日的日K线(盘中进行中的那根)。

    仅当快照的交易日期就是今天才合并,避免周末/节假日误加K线。
    """
    tradeDate = _quoteTradeDate(str(quote.get("time", "")))
    price = quote.get("price")
    if tradeDate != today or not price:
        return bars
    row = {
        "date": pd.Timestamp(tradeDate),
        "open": quote.get("open") or price,
        "high": quote.get("high") or price,
        "low": quote.get("low") or price,
        "close": price,
        "volume": quote.get("volume") or 0.0,
    }
    bars = bars.copy()
    lastDate = bars.iloc[-1]["date"].date()
    if lastDate == tradeDate:
        # 已有当日K线:用快照刷新最新价/量
        bars.loc[bars.index[-1], ["high", "low", "close", "volume"]] = [
            max(bars.iloc[-1]["high"], row["high"]),
            min(bars.iloc[-1]["low"], row["low"]),
            row["close"],
            row["volume"],
        ]
    elif lastDate < tradeDate:
        bars = pd.concat([bars, pd.DataFrame([row])], ignore_index=True)
    return bars


def _mergeTodayBar(market: str, symbol: str, bars: pd.DataFrame) -> pd.DataFrame:
    """尽力合并当日进行中K线,任何失败都返回原数据。"""
    try:
        provider = _buildProvider(market, operation="quotes")
        fetchQuotes = getattr(provider, "fetchQuotes", None)
        if not callable(fetchQuotes):
            return bars
        quote = fetchQuotes([symbol]).get(symbol)
        if not quote:
            return bars
        metadata = bars.attrs.get(META_KEY)
        if not metadata or metadata.get("source") != "tencent":
            return bars  # 未知/其他来源缓存不能直接拼接腾讯快照。
        expectedUnit = "lot100" if market == "cn" else "share"
        if metadata.get("instrumentId") != instrument(market, symbol)["instrumentId"] or metadata.get("volumeUnit") != expectedUnit:
            return bars
        tradeDate = _quoteTradeDate(str(quote.get("time", "")))
        if tradeDate is None:
            return bars
        if metadata.get("adjustment") != "none":
            # 当前价只能拼到当天取得的前复权基准，且昨收必须对得上。
            prior = bars.loc[bars["date"].dt.date < tradeDate]
            anchorDate = datetime.fromisoformat(metadata["fetchedAt"]).astimezone(ZoneInfo(ZONES[market])).date()
            previousClose = quote.get("prevClose")
            if metadata.get("adjustment") != "qfq" or anchorDate != tradeDate or prior.empty or previousClose is None:
                return bars
            if abs(float(prior.iloc[-1]["close"]) - previousClose) > 0.011:
                return bars
        rawTime = str(quote.get("time", ""))
        fmt = "%Y%m%d%H%M%S" if rawTime[:14].isdigit() else "%Y/%m/%d %H:%M:%S"
        observed = datetime.strptime(rawTime, fmt).replace(tzinfo=ZoneInfo(ZONES[market]))
        merged = _mergeQuoteBar(bars, quote, marketNow(market).date())
        return describeBars(merged, market, symbol, "day", source="tencent",
                            adjustment=metadata["adjustment"], volumeUnit=expectedUnit, observedAt=observed)
    except Exception:
        return bars


def _fetchAndCache(market: str, symbol: str, period: str) -> "pd.DataFrame | None":
    """按需抓取指定周期K线并缓存,失败返回 None。"""
    from datetime import date, timedelta

    end = marketNow(market).date()
    # 周/月线区间拉长,日线保持约 3 年
    start = end - timedelta(days=365 * (3 if period == "day" else 12))
    try:
        df = _buildProvider(market).fetchDailyBars(
            symbol, start.isoformat(), end.isoformat(), period=period
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{period} 行情抓取失败: {exc}") from exc
    if df.empty:
        return None
    saveBars(df, market, symbol, period=period, adjusted=True)
    return loadBars(market, symbol, period=period)


@router.post("/quotes", response_model=list[QuoteSnapshot])
def quotes(req: QuoteRequest) -> list[QuoteSnapshot]:
    """批量行情快照:按市场分组各发一次请求,供前端 3s 轮询。"""
    # 按市场分组,同一市场的代码合并成一次批量请求
    byMarket: dict[str, list[str]] = {}
    for item in req.items:
        byMarket.setdefault(item.market, []).append(item.symbol)

    snapshots: list[QuoteSnapshot] = []
    for market, symbols in byMarket.items():
        try:
            provider = _buildProvider(market, operation="quotes")
            fetchQuotes = getattr(provider, "fetchQuotes", None)
            if not callable(fetchQuotes):
                raw = {}
            else:
                raw = fetchQuotes(symbols)
        except Exception:
            # 单市场失败不影响其他市场,降级为占位
            raw = {}
        for symbol in symbols:
            q = raw.get(symbol)
            if q:
                snapshots.append(QuoteSnapshot(market=market, symbol=symbol, **q))
            else:
                snapshots.append(QuoteSnapshot(market=market, symbol=symbol))
    return snapshots


@router.get("/minute/{market}/{symbol}", response_model=MinuteResponse)
def minute(market: str, symbol: str) -> MinuteResponse:
    """当日分时数据(分钟线 + 均价 + 昨收)。"""
    provider = _buildProvider(market, operation="minute")
    fetchMinute = getattr(provider, "fetchMinute", None)
    if not callable(fetchMinute):
        raise HTTPException(status_code=400, detail=f"{market} 市场暂不支持分时数据")
    try:
        data = fetchMinute(symbol)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"分时数据获取失败: {exc}") from exc
    if not data["points"]:
        raise HTTPException(status_code=404, detail=f"{symbol} 今日暂无分时数据(非交易日?)")
    return MinuteResponse(market=market, symbol=symbol, **data)
