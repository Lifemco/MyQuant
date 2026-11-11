"""监控与自选股相关模型。"""
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.api import SymbolRequest


class WatchItemIn(SymbolRequest):
    """添加自选股请求。"""

    market: Literal["cn", "hk", "us"]
    symbol: str = Field(min_length=1, max_length=20)


class WatchItemOut(BaseModel):
    """自选股条目(含绑定的策略)。"""

    market: str
    symbol: str
    name: str
    strategy: str
    params: dict


class WatchItemUpdate(BaseModel):
    """更新自选股策略绑定。"""

    strategy: str
    params: dict = Field(default_factory=dict)


class SignalMarker(BaseModel):
    """单个买卖点标记。"""

    date: str
    type: Literal["buy", "sell"]
    price: float


class WatchOverviewItem(WatchItemOut):
    """自选列表行:策略状态 + 最新行情摘要。"""

    holding: bool
    lastSignal: SignalMarker | None
    close: float | None
    changePct: float | None
    dataInfo: dict | None = None
    dataAsOf: str | None = None
    signalAsOf: str | None = None
    error: str | None = None
    refreshError: str | None = None
    refreshedAt: str | None = None


class ChartRequest(SymbolRequest):
    """K线 + 信号图请求:可携带临时策略参数(不落地)。"""

    market: Literal["cn", "hk", "us"]
    symbol: str = Field(min_length=1, max_length=20)
    strategy: str
    params: dict = Field(default_factory=dict)
    period: Literal["day", "week", "month"] = "day"


class ChartResponse(BaseModel):
    """K线 + 买卖点标记 + 当前状态。"""

    bars: list[dict]
    markers: list[SignalMarker]
    holding: bool
    lastSignal: SignalMarker | None
    signalAsOf: str | None = None
    dataInfo: dict | None = None


class QuoteRequest(BaseModel):
    """批量行情快照请求。"""

    items: list[WatchItemIn] = Field(max_length=50)


class QuoteSnapshot(BaseModel):
    """单票行情快照(同花顺行情面板数据)。"""

    market: str
    symbol: str
    name: str = ""
    price: float | None = None
    prevClose: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    amount: float | None = None
    change: float | None = None
    changePct: float | None = None
    turnoverRate: float | None = None
    peRatio: float | None = None
    amplitude: float | None = None
    circulatingMarketCap: float | None = None
    totalMarketCap: float | None = None
    pbRatio: float | None = None
    time: str = ""
    source: str | None = None
    volumeUnit: str | None = None


class MinutePoint(BaseModel):
    """分时点:每分钟价格/均价/成交量。"""

    time: str
    price: float
    avg: float
    volume: float


class MinuteResponse(BaseModel):
    """当日分时数据。"""

    market: str
    symbol: str
    date: str
    prevClose: float | None
    points: list[MinutePoint]
