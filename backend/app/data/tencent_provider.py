"""A股/港股数据提供者:腾讯行情接口(web.ifzq.gtimg.cn / qt.gtimg.cn)。

选择腾讯而非东财/akshare 的原因:本机网络环境下东财 HTTPS 被阻断,
腾讯接口直连可用且无需代理。遵循系统代理环境配置。
"""
from datetime import datetime

import pandas as pd

from app.data.provider import DataProvider
from app.data.contract import describeBars
from app.core.validation import cnFullCode
from app.data import third_party

def _inferCnPrefix(symbol: str) -> str:
    """根据 A 股代码推断交易所前缀。"""
    if symbol.startswith(("4", "8", "920")):
        return "bj"
    if symbol.startswith(("6", "9")):
        return "sh"
    return "sz"


class TencentProvider(DataProvider):
    """腾讯行情实现,market 取 cn(A股)或 hk(港股),前复权。"""

    def __init__(self, market: str, adjustment: str | None = None) -> None:
        if market not in ("cn", "hk"):
            raise third_party.DataSourceRequestError(f"TencentProvider 仅支持 cn/hk,收到: {market}")
        self.market = market
        self.adjustment = adjustment

    def _fullCode(self, symbol: str) -> str:
        return f"hk{symbol}" if self.market == "hk" else cnFullCode(symbol)

    def fetchDailyBars(
        self, symbol: str, startDate: str, endDate: str, period: str = "day"
    ) -> pd.DataFrame:
        settings = third_party.providerSettings("tencent")
        if period not in settings["periods"]:
            raise third_party.DataSourceRequestError(f"不支持的周期: {period}")
        code = self._fullCode(symbol)
        from app.data.contract import instrument
        kind = instrument(self.market, symbol)["instrumentType"]
        adjustment = self.adjustment or ("none" if kind == "index" else settings["defaultAdjustment"])
        if adjustment not in settings["adjustments"] or (kind == "index" and adjustment != "none"):
            raise third_party.DataSourceRequestError("腾讯不支持该标的复权方式")
        payload = third_party.tencentHistory(code, startDate, endDate, period, adjustment)

        node = payload.get("data", {}).get(code, {})
        # 前复权键为 qfqday/qfqweek/qfqmonth,无复权数据时退化为 day/week/month
        adjustedKey = f"{adjustment}{period}" if adjustment != "none" else period
        rows = node.get(adjustedKey) or node.get(period) or []
        return describeBars(self._normalizeBars(rows), self.market, symbol, period,
                            source="tencent", adjustment=adjustment if node.get(adjustedKey) else "none",
                            volumeUnit=settings["volumeUnits"][self.market])

    @staticmethod
    def _normalizeBars(rows: list) -> pd.DataFrame:
        """字段顺序: [date, open, close, high, low, volume, ...附加信息]"""
        mapping = third_party.PROVIDERS["tencent"]["barFields"]
        records = [{field: row[index] for field, index in mapping.items()} for row in rows]
        df = pd.DataFrame(records)
        if df.empty:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["date"])
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.sort_values("date").reset_index(drop=True)

    def fetchMinute(self, symbol: str) -> dict:
        """当日分时数据:每分钟 {time, price, avg, volume},附昨收。

        分时格式: "0930 1239.53 161 19956433.00" → 时间/价格/成交量(手)/成交额(元)。
        均价 = 累计成交额 / 累计成交量(A股 1 手 = 100 股,港股成交量单位为股)。
        """
        code = self._fullCode(symbol)
        payload = third_party.tencentMinute(code)

        node = payload.get("data", {}).get(code, {})
        rawPoints = node.get("data", {}).get("data", [])
        # 昨收:分钟接口的 qt 快照里带昨日收盘价
        prevClose = None
        qt = node.get("qt", {}).get(code, [])
        previousCloseIndex = third_party.PROVIDERS["tencent"]["quoteFields"]["prevClose"]
        if len(qt) > previousCloseIndex:
            try:
                prevClose = float(qt[previousCloseIndex])
            except (TypeError, ValueError):
                prevClose = None

        lotSize = 100 if third_party.PROVIDERS["tencent"]["volumeUnits"][self.market] == "lot100" else 1
        # 收盘后腾讯会追加横盘尾巴(A股 15:00 后、港股 16:00 后),过滤掉
        maxTime = third_party.PROVIDERS["tencent"]["minuteCloseTimes"][self.market]
        return {
            "date": self._minuteTradeDate(node, code),
            "prevClose": prevClose,
            "points": self._parseMinutePoints(rawPoints, lotSize, maxTime),
        }

    @staticmethod
    def _minuteTradeDate(node: dict, code: str) -> str:
        raw = str(node.get("data", {}).get("date", ""))
        qt = node.get("qt", {}).get(code, [])
        timeIndex = third_party.PROVIDERS["tencent"]["quoteFields"]["time"]
        if not raw and len(qt) > timeIndex:
            raw = str(qt[timeIndex])
        for fmt, length in (("%Y%m%d", 8), ("%Y/%m/%d", 10), ("%Y-%m-%d", 10)):
            try:
                return datetime.strptime(raw[:length], fmt).date().isoformat()
            except ValueError:
                pass
        return ""  # 无上游日期时不捏造“今天”。

    @staticmethod
    def _parseMinutePoints(rawPoints: list[str], lotSize: int, maxTime: str = "15:00") -> list[dict]:
        """解析分时行:"0930 1239.53 161 19956433.00" → 时间/价格/累计量/累计额。

        注意接口返回累计值:每分钟量 = 当前累计 - 上一分钟累计;
        均价 = 累计成交额 / (累计成交量 × 每手股数)。
        """
        points: list[dict] = []
        cumVolume = 0.0
        cumAmount = 0.0
        for line in rawPoints:
            parts = line.split()
            if len(parts) < 4:
                continue
            positions = third_party.PROVIDERS["tencent"]["minuteFields"]
            hhmm = parts[positions["time"]]
            timeStr = f"{hhmm[:2]}:{hhmm[2:]}"
            if timeStr > maxTime:
                continue
            price, cumVol, cumAmt = (float(parts[positions[key]]) for key in ("price", "volume", "amount"))
            minuteVolume = cumVol - cumVolume
            cumVolume = cumVol
            cumAmount = cumAmt
            avg = round(cumAmount / (cumVolume * lotSize), 4) if cumVolume > 0 else price
            points.append(
                {
                    "time": timeStr,
                    "price": price,
                    "avg": avg,
                    "volume": minuteVolume,
                }
            )
        return points

    def fetchQuotes(self, symbols: list[str]) -> dict[str, dict]:
        """批量行情快照(一次请求多只),键为原始代码。"""
        if not symbols:
            return {}
        codes = [self._fullCode(s) for s in symbols]
        text = third_party.tencentRequest("quotes", codes=codes)
        result: dict[str, dict] = {}
        requested = dict(zip(codes, symbols))
        for block in text.strip().split(";"):
            if "=" not in block:
                continue
            fields = block.split("=", 1)[1].strip().strip('"').split("~")
            code = block.split("=", 1)[0].strip().removeprefix("v_")
            if code not in requested or len(fields) < 4 or fields[third_party.PROVIDERS["tencent"]["quoteCodeField"]] != code[2:]:
                continue
            result[requested[code]] = {**self._parseQuoteFields(fields), "source": "tencent",
                                      "volumeUnit": third_party.PROVIDERS["tencent"]["volumeUnits"][self.market]}
        return result

    @staticmethod
    def _parseQuoteFields(f: list[str]) -> dict:
        """解析快照字段(以 A 股布局为基准,港股公共字段位置一致)。"""
        def num(idx: int) -> float | None:
            try:
                value = float(f[idx])
                return value
            except (IndexError, TypeError, ValueError):
                return None

        settings = third_party.PROVIDERS["tencent"]
        result = {}
        for key, idx in settings["quoteFields"].items():
            if key in ("name", "time"):
                result[key] = f[idx] if len(f) > idx else ""
            else:
                value = num(idx)
                result[key] = value * settings["quoteScales"].get(key, 1) if value is not None else None
        return result


    def fetchName(self, symbol: str) -> str:
        """取股票名称,失败返回空串。"""
        try:
            quotes = self.fetchQuotes([symbol])
            for q in quotes.values():
                if q.get("name"):
                    return q["name"]
        except Exception:
            pass
        return ""
