"""行情口径：身份、单位、复权和采集时点必须随数据一起保存。"""
from datetime import datetime

import numpy as np
import pandas as pd

from app.core.validation import cnFullCode, validateSymbol
from app.monitor.session import closedBars, marketNow, ZONES

META_KEY = "marketData"
IDENTITY_FIELDS = ("instrumentId", "period", "adjustment", "volumeUnit", "currency", "priceUnit")


def instrument(market: str, symbol: str) -> dict:
    symbol = validateSymbol(market, symbol)
    code = cnFullCode(symbol) if market == "cn" else symbol
    isIndex = market == "cn" and ((code.startswith("sh000")) or code.startswith(("sz399", "bj899")))
    return {"market": market, "symbol": symbol, "instrumentId": f"{market}:{code}",
            "instrumentType": "index" if isIndex else "stock",
            "currency": {"cn": "CNY", "hk": "HKD", "us": "USD"}[market],
            "priceUnit": "point" if isIndex else "currency"}


def validateBars(frame: pd.DataFrame) -> pd.DataFrame:
    required = ["date", "open", "high", "low", "close", "volume"]
    if set(required) - set(frame):
        raise ValueError("行情缺少必要字段")
    df = frame.copy()
    df["date"] = pd.to_datetime(df["date"], errors="raise")
    if df["date"].dt.tz is not None:
        raise ValueError("交易日期应先转换为交易所本地日期")
    if not df["date"].equals(df["date"].dt.normalize()):
        raise ValueError("日/周/月线日期不能包含盘中时分秒")
    for column in required[1:]:
        df[column] = pd.to_numeric(df[column], errors="raise")
    if df["date"].isna().any() or not np.isfinite(df[required[1:]].to_numpy(dtype=float)).all():
        raise ValueError("行情包含缺失或非有限数值")
    if (df[["open", "high", "low", "close"]] <= 0).any().any() or (df["volume"] < 0).any():
        raise ValueError("价格必须为正且成交量不能为负")
    if ((df["high"] < df[["open", "low", "close"]].max(axis=1)) |
        (df["low"] > df[["open", "high", "close"]].min(axis=1))).any():
        raise ValueError("行情开高低收关系不合法")
    duplicates = df[df["date"].duplicated(keep=False)]
    if not duplicates.empty and (duplicates.groupby("date")[required[1:]].nunique() > 1).any().any():
        raise ValueError("同一日期返回了冲突的行情，不能静默覆盖")
    return df.drop_duplicates("date").sort_values("date").reset_index(drop=True)


def describeBars(frame: pd.DataFrame, market: str, symbol: str, period: str, *, source: str,
                 adjustment: str, volumeUnit: str, observedAt: datetime | None = None) -> pd.DataFrame:
    df = validateBars(frame)
    if volumeUnit not in ("share", "lot100"):
        raise ValueError("必须明确成交量单位，不能猜测每手股数")
    if adjustment not in ("none", "qfq", "hfq", "yahoo_auto_adjust"):
        raise ValueError("必须明确价格复权口径")
    now = marketNow(market)
    observed = observedAt or now
    if observed.tzinfo is None:
        raise ValueError("行情采集时间必须包含时区")
    df.attrs.pop(META_KEY, None)
    confirmed = closedBars(df, market, period, now=min(now, observed))
    df.attrs[META_KEY] = {**instrument(market, symbol), "period": period, "source": source,
                         "adjustment": adjustment, "volumeUnit": volumeUnit, "timezone": ZONES[market],
                         "fetchedAt": now.isoformat(), "observedAt": observed.isoformat(),
                         "confirmedThrough": str(confirmed["date"].max().date()) if len(confirmed) else None}
    return df


def compareDailyBars(left: pd.DataFrame, right: pd.DataFrame) -> dict:
    """仅核对同一标的已确认、不复权日线；不把计算字段作为交易事实比较。"""
    a, b = left.attrs.get(META_KEY), right.attrs.get(META_KEY)
    if not a or not b:
        raise ValueError("缺少来源/口径信息，不能确认数据可比较")
    if any(a.get(key) != b.get(key) for key in ("instrumentId", "currency", "priceUnit")):
        raise ValueError("不是同一标的或价格单位不同")
    if a.get("period") != "day" or b.get("period") != "day" or a.get("adjustment") != "none" or b.get("adjustment") != "none":
        raise ValueError("跨源核对须使用不复权日线，不能直接比较不同复权基准")
    factors = {"share": 1, "lot100": 100}
    if a.get("volumeUnit") not in factors or b.get("volumeUnit") not in factors:
        raise ValueError("成交量单位未知")
    l = closedBars(validateBars(left), a["market"])
    r = closedBars(validateBars(right), b["market"])
    l["volume"] *= factors[a["volumeUnit"]]
    r["volume"] *= factors[b["volumeUnit"]]
    merged = l.merge(r, on="date", suffixes=("_left", "_right"))
    differences = []
    for row in merged.to_dict("records"):
        for field in ("open", "high", "low", "close", "volume"):
            x, y = float(row[f"{field}_left"]), float(row[f"{field}_right"])
            tolerance = 1e-4 if field != "volume" else 1e-6
            if abs(x - y) > tolerance:
                differences.append({"date": str(row["date"].date()), "field": field, "left": x, "right": y})
    sameSource = a["source"] == b["source"]
    return {"comparedDates": len(merged), "differences": differences,
            "sameSource": sameSource, "independentSources": not sameSource,
            "matches": len(merged) > 0 and not differences}
