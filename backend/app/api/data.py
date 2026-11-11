"""数据管理接口:抓取、列表、读取行情。"""
from fastapi import APIRouter, HTTPException

from app.data.store import listSymbols, loadBars, saveBars
from app.data.tencent_provider import TencentProvider
from app.data.yfinance_provider import YFinanceProvider
from app.schemas.api import BarPoint, FetchBarsRequest, FetchBarsResponse, SymbolInfo

router = APIRouter(prefix="/api/data", tags=["data"])


def _buildProvider(market: str):
    """按市场选择数据提供者。"""
    if market == "us":
        return YFinanceProvider()
    return TencentProvider(market)


@router.post("/fetch", response_model=FetchBarsResponse)
def fetchBars(req: FetchBarsRequest) -> FetchBarsResponse:
    """从数据源抓取日线并写入本地 Parquet 缓存。"""
    try:
        df = _buildProvider(req.market).fetchDailyBars(req.symbol, req.startDate, req.endDate)
    except Exception as exc:  # 数据源异常统一转 502
        raise HTTPException(status_code=502, detail=f"数据源抓取失败: {exc}") from exc
    if df.empty:
        raise HTTPException(status_code=404, detail=f"未获取到 {req.symbol} 的行情数据")
    saveBars(df, req.market, req.symbol, adjusted=True)
    return FetchBarsResponse(
        market=req.market,
        symbol=req.symbol,
        rows=len(df),
        dataInfo=df.attrs.get("marketData"),
        startDate=str(df["date"].min().date()),
        endDate=str(df["date"].max().date()),
    )


@router.get("/symbols", response_model=list[SymbolInfo])
def getSymbols() -> list[SymbolInfo]:
    """列出本地已缓存的全部标的。"""
    return [SymbolInfo(**item) for item in listSymbols()]


@router.get("/bars/{market}/{symbol}", response_model=list[BarPoint])
def getBars(market: str, symbol: str) -> list[BarPoint]:
    """读取本地缓存的日线数据。"""
    df = loadBars(market, symbol)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"本地无 {market}/{symbol} 数据,请先抓取")
    return [
        BarPoint(
            date=str(row.date.date()),
            open=round(float(row.open), 4),
            high=round(float(row.high), 4),
            low=round(float(row.low), 4),
            close=round(float(row.close), 4),
            volume=float(row.volume),
        )
        for row in df.itertuples()
    ]
