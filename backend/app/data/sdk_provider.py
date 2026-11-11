"""AKShare/BaoStock适配：这里只做标准化和口径校验，外部调用在third_party。"""
import pandas as pd

from app.core.validation import cnFullCode, validateSymbol
from app.data.contract import describeBars, instrument
from app.data.provider import DataProvider
from app.data import third_party


class SDKProvider(DataProvider):
    def __init__(self, market: str, source: str, adjustment: str | None = None):
        self.market, self.source, self.adjustment = market, source, adjustment
        settings = third_party.providerSettings(source)
        if settings["driver"] != "sdk": raise third_party.DataSourceRequestError("不是SDK历史数据源")
        if market not in settings["markets"]: raise third_party.DataSourceRequestError(f"{source}不支持{market}")

    def fetchDailyBars(self, symbol: str, startDate: str, endDate: str, period: str = "day") -> pd.DataFrame:
        symbol = validateSymbol(self.market, symbol)
        settings = third_party.providerSettings(self.source)
        if period not in settings["periods"]: raise third_party.DataSourceRequestError("不支持该K线周期")
        kind = instrument(self.market, symbol)["instrumentType"]
        adjustment = self.adjustment or ("none" if kind == "index" else settings["defaultAdjustment"])
        if adjustment not in settings["adjustments"]: raise third_party.DataSourceRequestError("不支持该复权方式")
        if kind == "index" and adjustment != "none": raise third_party.DataSourceRequestError("指数行情必须使用不复权口径")
        if self.market == "cn" and cnFullCode(symbol)[:2] not in settings["exchanges"]:
            raise third_party.DataSourceRequestError("该来源尚未配置或验证此交易所支持")
        raw = third_party.requestSDKHistory(self.source, self.market, symbol, kind, startDate, endDate, period, adjustment)
        if raw.empty: return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        excluded = 0
        rowFilter = settings.get("excludeRows")
        if rowFilter and rowFilter["field"] in raw:
            excludedMask = raw[rowFilter["field"]].astype(str).eq(rowFilter["value"])
            excluded = int(excludedMask.sum())
            raw = raw.loc[~excludedMask].copy()
        df = raw.rename(columns=settings["columns"])
        df = df[["date", "open", "high", "low", "close", "volume"]].copy()
        df["date"] = pd.to_datetime(df["date"], errors="raise")
        df = df.loc[df["date"].between(pd.Timestamp(startDate), pd.Timestamp(endDate))]
        result = describeBars(df, self.market, symbol, period,
                              source=settings.get("source", self.source), adjustment=adjustment,
                              volumeUnit=settings["volumeUnits"][self.market])
        result.attrs["marketData"]["adapter"] = self.source
        if rowFilter: result.attrs["marketData"][rowFilter["countField"]] = excluded
        return result
