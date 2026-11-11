"""美股数据提供者,基于 yfinance。

国内网络访问 Yahoo 需要代理:优先读 QUANT_PROXY 环境变量,
其次回落到 macOS 系统代理设置,再写入 HTTPS_PROXY 供 curl_cffi 使用。
"""
import os
from urllib.request import getproxies

import pandas as pd

from app.data.provider import DataProvider


def _ensureProxy() -> None:
    """为 yfinance 配置代理环境变量(若尚未配置)。"""
    if os.environ.get("HTTPS_PROXY"):
        return
    proxy = os.environ.get("QUANT_PROXY") or getproxies().get("https") or getproxies().get("http")
    if proxy:
        os.environ["HTTPS_PROXY"] = proxy
        os.environ["HTTP_PROXY"] = proxy


class YFinanceProvider(DataProvider):
    """yfinance 实现,覆盖美股/ETF,默认前复权(auto_adjust)。"""

    # 周期 → yfinance interval
    _PERIOD_INTERVAL = {"day": "1d", "week": "1wk", "month": "1mo"}

    def fetchDailyBars(
        self, symbol: str, startDate: str, endDate: str, period: str = "day"
    ) -> pd.DataFrame:
        _ensureProxy()
        # 延迟导入:确保代理环境变量在 curl_cffi 初始化前生效
        import yfinance as yf

        interval = self._PERIOD_INTERVAL.get(period, "1d")
        raw = yf.download(
            symbol, start=startDate, end=endDate, interval=interval,
            auto_adjust=True, progress=False,
        )
        if raw.empty:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        # yfinance 多级列时拍平
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        df = raw.reset_index().rename(
            columns={
                "Date": "date", "Open": "open", "High": "high",
                "Low": "low", "Close": "close", "Volume": "volume",
            }
        )
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        keep = ["date", "open", "high", "low", "close", "volume"]
        return df[keep].sort_values("date").reset_index(drop=True)
