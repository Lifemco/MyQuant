"""当日K线合并逻辑单元测试(纯函数,无网络)。"""
from datetime import date

import pandas as pd
import pytest

from app.api.monitor import _mergeQuoteBar, _quoteTradeDate
from tests.conftest import makeBars

TODAY = date(2026, 9, 30)


class TestQuoteTradeDate:
    def test_cnFormat(self):
        assert _quoteTradeDate("20260930100310") == TODAY

    def test_hkFormat(self):
        assert _quoteTradeDate("2026/09/30 09:48:04") == TODAY

    def test_invalidReturnsNone(self):
        assert _quoteTradeDate("") is None
        assert _quoteTradeDate("abc") is None


def _quote(time: str, price: float = 18.28) -> dict:
    return {
        "time": time,
        "price": price,
        "open": 18.0,
        "high": 18.5,
        "low": 17.9,
        "volume": 12345.0,
    }


class TestMergeQuoteBar:
    def test_appendsTodayBar(self):
        # 缓存到昨天 → 追加今日进行中的K线
        bars = makeBars([17.0, 17.5], start="2026-09-28")  # 最后一根 2026-09-29
        merged = _mergeQuoteBar(bars, _quote("20260930100310"), TODAY)
        assert len(merged) == 3
        last = merged.iloc[-1]
        assert last["date"].date() == TODAY
        assert last["close"] == 18.28
        assert last["open"] == 18.0

    def test_updatesExistingTodayBar(self):
        # 已有当日K线 → 更新收盘价,且 high/low 取极值
        bars = makeBars([17.5, 17.9], start="2026-09-29")  # 最后一根即 2026-09-30
        merged = _mergeQuoteBar(bars, _quote("20260930100310"), TODAY)
        assert len(merged) == 2
        last = merged.iloc[-1]
        assert last["close"] == 18.28
        assert last["high"] == 18.5  # 快照高点更高则抬升
        # 快照低点 17.9 高于原低点 17.9*0.98=17.542 → 保留原低点
        assert last["low"] == pytest.approx(17.542, abs=0.001)

    def test_weekendQuoteIgnored(self):
        # 快照是周五的(今天周日)→ 不合并
        bars = makeBars([17.0], start="2026-09-25")
        merged = _mergeQuoteBar(bars, _quote("20260925150310"), date(2026, 9, 27))
        assert len(merged) == 1

    def test_noPriceIgnored(self):
        bars = makeBars([17.0], start="2026-09-29")
        q = _quote("20260930100310")
        q["price"] = None
        merged = _mergeQuoteBar(bars, q, TODAY)
        assert len(merged) == 1
