"""腾讯 provider 解析逻辑单元测试(样本数据,无网络依赖)。"""
import pandas as pd
import pytest

from app.data.store import listSymbols, loadBars, saveBars
from app.data.tencent_provider import TencentProvider
from tests.conftest import makeBars

# 真实抓取的 A 股快照样本(字段位置以腾讯协议为准)
SAMPLE_CN_QUOTE = (
    'v_sh600519="1~贵州茅台~600519~1237.48~1235.58~1239.53~5550~2645~2905~'
    "1237.44~7~1237.42~3~1237.41~5~1237.40~2~1237.13~10~1237.61~2~1237.63~6~"
    "1237.64~3~1237.65~5~1237.80~1~~20260930100310~1.90~0.15~1244.00~1236.05~"
    "1237.48/5550/687651298~5550~68765~0.04~19.00~~1244.00~1236.05~0.64~"
    '15469.51~15469.51~6.16~1359.14~1112.02~1.39~10~1238.94~";'
)

SAMPLE_MINUTE_LINES = [
    "0930 1239.53 161 19956433.00",  # 时间 价格 量(手) 额(元)
    "0931 1238.25 993 123198500.61",
    "0932 1237.50 1248 154779435.60",
]


class TestQuoteParsing:
    def test_parseCnQuoteFields(self):
        fields = SAMPLE_CN_QUOTE.split("=", 1)[1].strip().strip('"').split("~")
        q = TencentProvider._parseQuoteFields(fields)
        assert q["name"] == "贵州茅台"
        assert q["price"] == 1237.48
        assert q["prevClose"] == 1235.58
        assert q["open"] == 1239.53
        assert q["high"] == 1244.00
        assert q["low"] == 1236.05
        assert q["changePct"] == pytest.approx(0.0015)
        assert q["turnoverRate"] == 0.04
        assert q["peRatio"] == 19.00
        assert q["totalMarketCap"] == 15469.51  # 亿
        assert q["amount"] == pytest.approx(68765 * 10000)  # 万元转元

    def test_shortFieldsDegradeGracefully(self):
        q = TencentProvider._parseQuoteFields(["100", "腾讯控股", "00700", "425.2"])
        assert q["name"] == "腾讯控股"
        assert q["price"] == 425.2
        assert q["high"] is None


class TestMinuteAvgPrice:
    def test_avgEqualsCumAmountOverCumVolume(self):
        # 接口的成交额本身就是累计值:均价 = 累计成交额 / (累计手数 * 100)
        points = TencentProvider._parseMinutePoints(SAMPLE_MINUTE_LINES, lotSize=100)
        # 09:31: 123198500.61 / (993 * 100) = 1240.6697
        assert points[1]["avg"] == pytest.approx(1240.6697, abs=0.001)
        # 09:32: 154779435.60 / (1248 * 100) = 1240.2198
        assert points[2]["avg"] == pytest.approx(1240.2198, abs=0.001)

    def test_volumeIsPerMinuteNotCumulative(self):
        # 接口返回累计量:逐分钟量 = 差分(993-161=832)
        points = TencentProvider._parseMinutePoints(SAMPLE_MINUTE_LINES, lotSize=100)
        assert points[0]["volume"] == 161.0
        assert points[1]["volume"] == 832.0
        assert points[2]["volume"] == 255.0

    def test_timeFormatted(self):
        points = TencentProvider._parseMinutePoints(SAMPLE_MINUTE_LINES, lotSize=100)
        assert points[0]["time"] == "09:30"


class TestPeriodStorePaths:
    def test_weekBarsStoredSeparately(self, tmp_path):
        saveBars(makeBars([1.0, 2.0]), "cn", "600519", dataDir=tmp_path)
        saveBars(makeBars([1.5, 2.5]), "cn", "600519", period="week", dataDir=tmp_path)
        day = loadBars("cn", "600519", dataDir=tmp_path)
        week = loadBars("cn", "600519", period="week", dataDir=tmp_path)
        assert list(day["close"]) == [1.0, 2.0]
        assert list(week["close"]) == [1.5, 2.5]

    def test_listSymbolsSkipsPeriodFiles(self, tmp_path):
        saveBars(makeBars([1.0]), "cn", "600519", dataDir=tmp_path)
        saveBars(makeBars([1.5]), "cn", "600519", period="month", dataDir=tmp_path)
        symbols = listSymbols(dataDir=tmp_path)
        assert len(symbols) == 1 and symbols[0]["symbol"] == "600519"


class TestMinuteCloseFilter:
    def test_postClosePointsFiltered(self):
        # 收盘后的横盘尾巴(15:01 起)应被过滤
        lines = SAMPLE_MINUTE_LINES + [
            "1500 1237.00 1300 160000000.00",
            "1501 1237.00 1300 160000000.00",
            "1510 1237.00 1300 160000000.00",
        ]
        points = TencentProvider._parseMinutePoints(lines, lotSize=100)
        assert points[-1]["time"] == "15:00"
        assert len(points) == 4

    def test_hkCloseAt1600(self):
        lines = SAMPLE_MINUTE_LINES + ["1600 300.00 9000 2700000.00", "1608 300.00 9000 2700000.00"]
        points = TencentProvider._parseMinutePoints(lines, lotSize=1, maxTime="16:00")
        assert points[-1]["time"] == "16:00"
