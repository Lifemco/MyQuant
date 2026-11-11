"""数据提供者抽象基类:统一各市场的行情获取接口。"""
from abc import ABC, abstractmethod

import pandas as pd


class DataProvider(ABC):
    """行情数据提供者,每个市场一个实现。"""

    @abstractmethod
    def fetchDailyBars(
        self, symbol: str, startDate: str, endDate: str, period: str = "day"
    ) -> pd.DataFrame:
        """抓取K线行情。

        Args:
            symbol: 标的代码,如 600519 / 00700 / AAPL。
            startDate: 开始日期 YYYY-MM-DD。
            endDate: 结束日期 YYYY-MM-DD。
            period: 周期 day/week/month。

        Returns:
            标准列 [date, open, high, low, close, volume] 的 DataFrame,
            date 为 datetime64,按日期升序。
        """
        raise NotImplementedError
