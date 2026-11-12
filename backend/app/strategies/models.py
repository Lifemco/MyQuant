from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.api import SymbolRequest


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class Operand(StrictModel):
    kind: Literal["constant", "close", "open", "high", "low", "volume", "sma", "rsi", "return", "volatility", "drawdown", "volume_ratio", "external"]
    value: float | None = Field(default=None, strict=True)
    window: int = Field(default=20, ge=2, le=252, strict=True)
    factor: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,39}$")
    maxAgeDays: int = Field(default=90, ge=1, le=366, strict=True)

    @model_validator(mode="after")
    def requiredValues(self):
        if self.kind == "constant" and self.value is None:
            raise ValueError("常数需要value")
        if self.kind == "external" and not self.factor:
            raise ValueError("外部因子需要factor名称")
        if self.kind != "constant" and self.value is not None:
            raise ValueError("仅常数允许value")
        if self.kind != "external" and self.factor is not None:
            raise ValueError("仅外部因子允许factor")
        return self


class Condition(StrictModel):
    left: Operand
    op: Literal["gt", "gte", "lt", "lte", "cross_above", "cross_below"]
    right: Operand


class RuleGroup(StrictModel):
    logic: Literal["all", "any"] = "all"
    conditions: list[Condition] = Field(min_length=1, max_length=12)


class StrategySpec(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=2000)
    entry: RuleGroup
    exit: RuleGroup
    stopLossPct: float | None = Field(default=None, gt=0, lt=1, strict=True)
    takeProfitPct: float | None = Field(default=None, gt=0, le=10, strict=True)
    maxHoldingBars: int | None = Field(default=None, ge=1, le=1000, strict=True)


class DraftRequest(StrictModel):
    prompt: str = Field(min_length=2, max_length=8000)


class AgentDraft(StrictModel):
    summary: str = Field(max_length=4000)
    spec: StrategySpec | None = None
    questions: list[str] = Field(default_factory=list, max_length=12)
    unsupported: list[str] = Field(default_factory=list, max_length=12)


class SaveStrategy(StrictModel):
    id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    version: int | None = Field(default=None, ge=1)
    spec: StrategySpec
    prompt: str = Field(default="", max_length=8000)
    summary: str = Field(default="", max_length=4000)


class ExecuteStrategy(StrictModel):
    spec: StrategySpec
    symbols: list[SymbolRequest] = Field(min_length=1, max_length=20)
    feeRate: float = Field(default=0.0003, ge=0, le=0.01)

    @model_validator(mode="after")
    def uniqueSymbols(self):
        if len({(s.market, s.symbol) for s in self.symbols}) != len(self.symbols):
            raise ValueError("执行标的不能重复")
        return self


class Observation(StrictModel):
    availableAt: datetime
    value: float = Field(strict=True)

    @field_validator("availableAt")
    @classmethod
    def awareTime(cls, value):
        if value.tzinfo is None:
            raise ValueError("因子发布时间必须包含时区，不能只填财报所属日期")
        return value


class FactorUpload(SymbolRequest):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    factor: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    source: str = Field(min_length=1, max_length=200)
    observations: list[Observation] = Field(min_length=1, max_length=20000)
