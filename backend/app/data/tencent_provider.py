"""A股/港股数据提供者:腾讯行情接口(web.ifzq.gtimg.cn / qt.gtimg.cn)。

选择腾讯而非东财/akshare 的原因:本机网络环境下东财 HTTPS 被阻断,
腾讯接口直连可用且无需代理。遵循系统代理环境配置。
"""
from datetime import datetime

import httpx
import pandas as pd

from app.data.provider import DataProvider
from app.data.contract import describeBars
from app.core.validation import cnFullCode

TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
TENCENT_MINUTE_URL = "https://web.ifzq.gtimg.cn/appstock/app/minute/query"
TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="

# 单次请求的最大K线根数(腾讯上限约 640)
MAX_BARS_PER_REQUEST = 640

# 支持的K线周期
SUPPORTED_PERIODS = ("day", "week", "month")


def _inferCnPrefix(symbol: str) -> str:
    """根据 A 股代码推断交易所前缀。"""
    if symbol.startswith(("4", "8", "920")):
        return "bj"
    if symbol.startswith(("6", "9")):
        return "sh"
    return "sz"


class TencentProvider(DataProvider):
    """腾讯行情实现,market 取 cn(A股)或 hk(港股),前复权。"""

    def __init__(self, market: str) -> None:
        if market not in ("cn", "hk"):
            raise ValueError(f"TencentProvider 仅支持 cn/hk,收到: {market}")
        self.market = market

    def _fullCode(self, symbol: str) -> str:
        return f"hk{symbol}" if self.market == "hk" else cnFullCode(symbol)

    def fetchDailyBars(
        self, symbol: str, startDate: str, endDate: str, period: str = "day"
    ) -> pd.DataFrame:
        if period not in SUPPORTED_PERIODS:
            raise ValueError(f"不支持的周期: {period},可选 {SUPPORTED_PERIODS}")
        code = self._fullCode(symbol)
        # 周线/月线不传日期区间,按根数回溯(640 周 ≈ 12 年)
        if period == "day":
            param = f"{code},day,{startDate},{endDate},{MAX_BARS_PER_REQUEST},qfq"
        else:
            param = f"{code},{period},,,{MAX_BARS_PER_REQUEST},qfq"
        # 遵循运行环境的代理和CA配置
        with httpx.Client(trust_env=True, timeout=30) as client:
            resp = client.get(TENCENT_KLINE_URL, params={"param": param})
            resp.raise_for_status()
            payload = resp.json()

        node = payload.get("data", {}).get(code, {})
        # 前复权键为 qfqday/qfqweek/qfqmonth,无复权数据时退化为 day/week/month
        rows = node.get(f"qfq{period}") or node.get(period) or []
        return describeBars(self._normalizeBars(rows), self.market, symbol, period,
                            source="tencent", adjustment="qfq" if node.get(f"qfq{period}") else "none",
                            volumeUnit="lot100" if self.market == "cn" else "share")

    @staticmethod
    def _normalizeBars(rows: list) -> pd.DataFrame:
        """字段顺序: [date, open, close, high, low, volume, ...附加信息]"""
        records = [
            {
                "date": row[0],
                "open": row[1],
                "close": row[2],
                "high": row[3],
                "low": row[4],
                "volume": row[5],
            }
            for row in rows
        ]
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
        with httpx.Client(trust_env=True, timeout=15) as client:
            resp = client.get(TENCENT_MINUTE_URL, params={"code": code})
            resp.raise_for_status()
            payload = resp.json()

        node = payload.get("data", {}).get(code, {})
        rawPoints = node.get("data", {}).get("data", [])
        # 昨收:分钟接口的 qt 快照里带昨日收盘价
        prevClose = None
        qt = node.get("qt", {}).get(code, [])
        if len(qt) > 4:
            try:
                prevClose = float(qt[4])
            except (TypeError, ValueError):
                prevClose = None

        lotSize = 100 if self.market == "cn" else 1
        # 收盘后腾讯会追加横盘尾巴(A股 15:00 后、港股 16:00 后),过滤掉
        maxTime = "15:00" if self.market == "cn" else "16:00"
        return {
            "date": self._minuteTradeDate(node, code),
            "prevClose": prevClose,
            "points": self._parseMinutePoints(rawPoints, lotSize, maxTime),
        }

    @staticmethod
    def _minuteTradeDate(node: dict, code: str) -> str:
        raw = str(node.get("data", {}).get("date", ""))
        qt = node.get("qt", {}).get(code, [])
        if not raw and len(qt) > 30:
            raw = str(qt[30])
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
            hhmm = parts[0]
            timeStr = f"{hhmm[:2]}:{hhmm[2:]}"
            if timeStr > maxTime:
                continue
            price, cumVol, cumAmt = float(parts[1]), float(parts[2]), float(parts[3])
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
        with httpx.Client(trust_env=True, timeout=10) as client:
            resp = client.get(f"{TENCENT_QUOTE_URL}{','.join(codes)}")
            resp.raise_for_status()
        text = resp.content.decode("gbk", errors="ignore")
        result: dict[str, dict] = {}
        requested = dict(zip(codes, symbols))
        for block in text.strip().split(";"):
            if "=" not in block:
                continue
            fields = block.split("=", 1)[1].strip().strip('"').split("~")
            code = block.split("=", 1)[0].strip().removeprefix("v_")
            if code not in requested or len(fields) < 4 or fields[2] != code[2:]:
                continue
            result[requested[code]] = {**self._parseQuoteFields(fields), "source": "tencent",
                                      "volumeUnit": "lot100" if self.market == "cn" else "share"}
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

        return {
            "name": f[1] if len(f) > 1 else "",
            "price": num(3),
            "prevClose": num(4),
            "open": num(5),
            "volume": num(6),  # 成交量(A股为手)
            "time": f[30] if len(f) > 30 else "",
            "change": num(31),
            "changePct": (num(32) or 0) / 100 if num(32) is not None else None,
            "high": num(33),
            "low": num(34),
            "amount": (num(37) or 0) * 10000 if num(37) is not None else None,  # 万元 → 元
            "turnoverRate": num(38),
            "peRatio": num(39),
            "amplitude": num(43),
            "circulatingMarketCap": num(44),  # 亿
            "totalMarketCap": num(45),  # 亿
            "pbRatio": num(46),
        }

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
