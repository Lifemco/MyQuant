"""数据管理接口:抓取、列表、读取行情。"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from typing import Literal
from urllib.parse import quote
import pandas as pd

from app.data.store import listSymbols, loadBars, saveBars
from app.data.third_party import makeProvider, listProviders, DataSourceRequestError
from app.schemas.api import BarPoint, FetchBarsRequest, FetchBarsResponse, DownloadBarsResponse, SymbolInfo
from app.data.contract import describeBars

router = APIRouter(prefix="/api/data", tags=["data"])


def _buildProvider(market: str, source: str | None = None, adjustment: str | None = None, operation: str = "history"):
    return makeProvider(market, source, adjustment, operation)


@router.get("/providers")
def providers() -> list[dict]:
    return listProviders()


def _requestBars(req: FetchBarsRequest):
    provider = _buildProvider(req.market, req.source, req.adjustment)
    try:
        df = provider.fetchDailyBars(req.symbol, req.startDate, req.endDate, period=req.period)
    except DataSourceRequestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"数据源抓取失败: {exc}") from exc
    if df.empty:
        raise HTTPException(status_code=404, detail=f"未获取到 {req.symbol} 的行情数据")
    metadata = df.attrs.get("marketData")
    df = df.loc[df["date"].between(pd.Timestamp(req.startDate), pd.Timestamp(req.endDate))].copy()
    if df.empty:
        raise HTTPException(status_code=404, detail="请求日期范围内没有行情")
    if metadata:
        from datetime import datetime
        df = describeBars(df, req.market, req.symbol, req.period, source=metadata["source"],
                          adjustment=metadata["adjustment"], volumeUnit=metadata["volumeUnit"],
                          observedAt=datetime.fromisoformat(metadata["observedAt"]))
        for key in ("adapter", "excludedSuspendedRows"):
            if key in metadata: df.attrs["marketData"][key] = metadata[key]
    return df


def _summary(req, df):
    return dict(market=req.market, symbol=req.symbol, rows=len(df), dataInfo=df.attrs.get("marketData"),
                startDate=str(df["date"].min().date()), endDate=str(df["date"].max().date()))


@router.post("/fetch", response_model=FetchBarsResponse)
def fetchBars(req: FetchBarsRequest) -> FetchBarsResponse:
    """按指定来源抓取并缓存；显式replaceCache才备份切换现有缓存。"""
    df = _requestBars(req)
    saveBars(df, req.market, req.symbol, period=req.period, adjusted=True, replace=req.replaceCache)
    return FetchBarsResponse(**_summary(req, df))


@router.post("/download", response_model=DownloadBarsResponse)
def downloadBars(req: FetchBarsRequest, format: Literal["json", "csv"] = "json"):
    """直接返回JSON或CSV文件，来源可选；不写入活动缓存。"""
    df = _requestBars(req)
    metadata = df.attrs.get("marketData", {})
    filename = f"{req.source or metadata.get('source', 'market')}_{req.market}_{req.symbol}_{req.startDate}_{req.endDate}.{format}"
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
    if format == "csv":
        output = df.copy()
        output["date"] = output["date"].dt.strftime("%Y-%m-%d")
        # CSV携带口径列，离开工作台后也不会丢失来源、单位和复权信息。
        for key, value in metadata.items(): output[f"meta_{key}"] = value
        return Response(content=output.to_csv(index=False).encode("utf-8-sig"), media_type="text/csv", headers=headers)
    result = DownloadBarsResponse(**_summary(req, df), bars=[
        BarPoint(date=str(row.date.date()), open=float(row.open), high=float(row.high), low=float(row.low),
                 close=float(row.close), volume=float(row.volume)) for row in df.itertuples()
    ])
    return Response(content=result.model_dump_json(), media_type="application/json", headers=headers)


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
