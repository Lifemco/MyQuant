"""请求/响应模型(Pydantic)。"""
from typing import Literal
from datetime import date

from pydantic import BaseModel, Field, model_validator

from app.core.validation import validateSymbol


class SymbolRequest(BaseModel):
    market: Literal["cn", "hk", "us"]
    symbol: str = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validSymbol(self):
        self.symbol = validateSymbol(self.market, self.symbol)
        return self


class FetchBarsRequest(SymbolRequest):
    startDate: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    endDate: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

    @model_validator(mode="after")
    def validDates(self):
        if date.fromisoformat(self.startDate) > date.fromisoformat(self.endDate):
            raise ValueError("开始日期不能晚于结束日期")
        return self


class FetchBarsResponse(BaseModel):
    market: str
    symbol: str
    rows: int
    startDate: str | None
    endDate: str | None


class SymbolInfo(BaseModel):
    market: str
    symbol: str
    rows: int
    startDate: str | None
    endDate: str | None


class BarPoint(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class RunBacktestRequest(SymbolRequest):
    strategy: str
    params: dict = Field(default_factory=dict)
    feeRate: float = Field(default=0.0003, ge=0, le=0.01)


class BacktestMetrics(BaseModel):
    totalReturn: float
    annualReturn: float
    annualVolatility: float
    sharpeRatio: float
    maxDrawdown: float
    calmarRatio: float
    totalTrades: int
    winRate: float


class EquityPoint(BaseModel):
    date: str
    equity: float


class Trade(BaseModel):
    entryDate: str
    exitDate: str | None
    pnlPct: float
    entryPrice: float | None = None
    exitPrice: float | None = None


class RunBacktestResponse(BaseModel):
    metrics: BacktestMetrics
    equityCurve: list[EquityPoint]
    trades: list[Trade]
    bars: list[BarPoint]


class StrategyMeta(BaseModel):
    name: str
    label: str
    desc: str = ""
    paramsSchema: dict


class ApiError(BaseModel):
    detail: str


class BatchBacktestRequest(BaseModel):
    """批量回测:同一策略跑多个标的。"""

    symbols: list[SymbolRequest] = Field(min_length=1, max_length=20)  # [{market, symbol}]
    strategy: str
    params: dict = Field(default_factory=dict)
    feeRate: float = Field(default=0.0003, ge=0, le=0.01)


class BatchResultItem(BaseModel):
    market: str
    symbol: str
    metrics: BacktestMetrics | None = None
    error: str | None = None


class OptimizeRequest(SymbolRequest):
    """参数寻优:网格扫描,返回按夏普降序的结果。"""

    market: Literal["cn", "hk", "us"]
    symbol: str = Field(min_length=1, max_length=20)
    strategy: str
    grid: dict[str, list[float]]  # {参数名: [候选值]}
    feeRate: float = Field(default=0.0003, ge=0, le=0.01)


class OptimizeResultItem(BaseModel):
    params: dict[str, float]
    metrics: BacktestMetrics
