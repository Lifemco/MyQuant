"""本地行情存储:每个标的存一个 Parquet 文件,按日期去重合并。"""
from pathlib import Path

import pandas as pd

from app.core.config import DATA_DIR


def _barPath(market: str, symbol: str, period: str = "day", dataDir: Path | None = None) -> Path:
    root = (dataDir or DATA_DIR) / market
    root.mkdir(parents=True, exist_ok=True)
    # 日线保持原文件名,周/月线带周期后缀
    filename = f"{symbol}.parquet" if period == "day" else f"{symbol}.{period}.parquet"
    return root / filename


def saveBars(
    df: pd.DataFrame, market: str, symbol: str, period: str = "day", dataDir: Path | None = None
) -> Path:
    """保存K线数据;已存在则按 date 合并去重(新数据优先)。"""
    path = _barPath(market, symbol, period, dataDir)
    if path.exists():
        old = pd.read_parquet(path)
        df = pd.concat([old, df]).drop_duplicates(subset="date", keep="last")
    df = df.sort_values("date").reset_index(drop=True)
    df.to_parquet(path, index=False)
    return path


def loadBars(
    market: str, symbol: str, period: str = "day", dataDir: Path | None = None
) -> pd.DataFrame | None:
    """读取本地K线,不存在返回 None。"""
    path = _barPath(market, symbol, period, dataDir)
    if not path.exists():
        return None
    return pd.read_parquet(path)


def listSymbols(dataDir: Path | None = None) -> list[dict]:
    """列出所有已缓存标的(仅统计日线文件)及其日期范围、行数。"""
    root = dataDir or DATA_DIR
    result: list[dict] = []
    if not root.exists():
        return result
    for marketDir in sorted(p for p in root.iterdir() if p.is_dir()):
        for file in sorted(marketDir.glob("*.parquet")):
            # 跳过周/月线文件(文件名形如 600519.week.parquet)
            if file.stem.count(".") > 0:
                continue
            df = pd.read_parquet(file, columns=["date"])
            result.append(
                {
                    "market": marketDir.name,
                    "symbol": file.stem,
                    "rows": len(df),
                    "startDate": str(df["date"].min().date()) if len(df) else None,
                    "endDate": str(df["date"].max().date()) if len(df) else None,
                }
            )
    return result
