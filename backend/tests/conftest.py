"""构造测试用行情数据的工具函数。"""
import numpy as np
import pandas as pd


def makeBars(closes: list[float], start: str = "2024-01-01") -> pd.DataFrame:
    """根据收盘价序列构造标准 OHLCV 数据,open/high/low 围绕 close 简单展开。"""
    dates = pd.bdate_range(start=start, periods=len(closes))
    arr = np.array(closes, dtype=float)
    return pd.DataFrame(
        {
            "date": dates,
            "open": arr * 0.99,
            "high": arr * 1.01,
            "low": arr * 0.98,
            "close": arr,
            "volume": 1_000_000.0,
        }
    )
