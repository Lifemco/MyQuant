"""按交易所时区保守确认已结束的K线，不将盘中数据用作正式信号。"""
from calendar import monthrange
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

ZONES = {"cn": "Asia/Shanghai", "hk": "Asia/Hong_Kong", "us": "America/New_York"}
# 港股收市竞价通常在16:08~16:10结束，16:10后才确认。
CLOSES = {"cn": time(15, 0), "hk": time(16, 10), "us": time(16, 0)}


def marketNow(market: str) -> datetime:
    return datetime.now(ZoneInfo(ZONES[market]))


def closedBars(bars: pd.DataFrame, market: str, period: str = "day", now: datetime | None = None) -> pd.DataFrame:
    current = (now or marketNow(market)).astimezone(ZoneInfo(ZONES[market]))
    metadata = bars.attrs.get("marketData")
    if metadata:
        # 采集于盘中的K线不会因服务器时钟走到晚上就自动变成收盘数据。
        observed = datetime.fromisoformat(metadata["observedAt"])
        current = min(current, observed.astimezone(ZoneInfo(ZONES[market])))
    def closed(value):
        end = pd.Timestamp(value).date()
        if period == "week":
            end += timedelta(days=(4 - end.weekday()) % 7)
        elif period == "month":
            end = end.replace(day=monthrange(end.year, end.month)[1])
        return end < current.date() or (end == current.date() and current.time() >= CLOSES[market])
    mask = bars["date"].map(closed)
    if metadata:
        cutoff = metadata.get("confirmedThrough")
        if cutoff is None:
            return bars.iloc[:0].copy()
        mask &= bars["date"] <= pd.Timestamp(cutoff)
    return bars.loc[mask].copy()
