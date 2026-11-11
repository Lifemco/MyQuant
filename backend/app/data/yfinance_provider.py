"""美股数据提供者,基于 yfinance。

国内网络访问 Yahoo 需要代理:优先读 QUANT_PROXY 环境变量,
其次回落到 macOS 系统代理设置,再写入 HTTPS_PROXY 供 curl_cffi 使用。
"""
import pandas as pd

from app.data.provider import DataProvider
from app.data.contract import describeBars
from app.data import third_party


class YFinanceProvider(DataProvider):
    """yfinance 实现,覆盖美股/ETF,默认前复权(auto_adjust)。"""

    def __init__(self, adjustment: str | None = None):
        self.adjustment = adjustment

    def fetchDailyBars(
        self, symbol: str, startDate: str, endDate: str, period: str = "day"
    ) -> pd.DataFrame:
        settings = third_party.providerSettings("yahoo")
        adjustment = self.adjustment or settings["defaultAdjustment"]
        if period not in settings["periods"] or adjustment not in settings["adjustments"]:
            raise third_party.DataSourceRequestError("Yahoo周期或复权方式不支持")
        raw = third_party.yahooHistory(symbol, startDate, endDate, period, adjustment)
        if raw.empty:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        # yfinance 多级列时拍平
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        df = raw.reset_index().rename(columns=settings["columns"])
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        keep = ["date", "open", "high", "low", "close", "volume"]
        return describeBars(df[keep], "us", symbol, period, source="yahoo",
                            adjustment=adjustment, volumeUnit=settings["volumeUnits"]["us"])
