"""本地行情存储：安全路径、写事务、原子替换及复权历史一致性。"""
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

from app.core.config import DATA_DIR
from app.core.files import atomicFile, fileLock
from app.core.validation import validateSymbol
from app.data.contract import META_KEY, IDENTITY_FIELDS, instrument, validateBars


def _barPath(market: str, symbol: str, period: str = "day", dataDir: Path | None = None) -> Path:
    symbol = validateSymbol(market, symbol)
    if period not in ("day", "week", "month"):
        raise ValueError("不支持的K线周期")
    base = (dataDir or DATA_DIR).resolve()
    root = base / market
    filename = f"{symbol}.parquet" if period == "day" else f"{symbol}.{period}.parquet"
    path = (root / filename).resolve()
    if not path.is_relative_to(base):
        raise ValueError("行情路径超出数据目录")
    root.mkdir(parents=True, exist_ok=True)
    return path


def saveBars(df: pd.DataFrame, market: str, symbol: str, period: str = "day",
             dataDir: Path | None = None, *, adjusted: bool = False, replace: bool = False) -> Path:
    """增量合并；复权历史修订时备份旧文件，以本次数据源窗口完整重建。

    不猜测复权因子，不拼接两套价格基准。重建可能缩短历史窗口，attrs记录原因。
    """
    path = _barPath(market, symbol, period, dataDir)
    df = validateBars(df)
    info = df.attrs.get(META_KEY)
    if info:
        expected = {**instrument(market, symbol), "period": period}
        if any(info.get(key) != value for key, value in expected.items()):
            raise ValueError("行情标的身份或周期与写入目标不一致")
        if info.get("volumeUnit") not in ("share", "lot100") or not info.get("source"):
            raise ValueError("行情来源或成交量单位不明确")
    numeric = df[["open", "high", "low", "close", "volume"]]
    if df.empty or df["date"].isna().any() or not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("行情为空或包含缺失/非有限数值")
    if (df[["open", "high", "low", "close"]] <= 0).any().any() or (df["volume"] < 0).any():
        raise ValueError("价格必须为正且成交量不能为负")
    with fileLock(path):
        if path.exists():
            old = pd.read_parquet(path)
            oldInfo = old.attrs.get(META_KEY)
            if oldInfo and not info:
                raise ValueError("新数据缺少来源或行情口径，不能覆盖已确认口径的缓存")
            reset = replace or bool(info) != bool(oldInfo)
            if info and oldInfo and not replace:
                if info.get("source") != oldInfo.get("source") or any(info.get(k) != oldInfo.get(k) for k in IDENTITY_FIELDS):
                    raise ValueError("数据源、标的或行情口径不一致，不能直接拼接；请先跨源核对并独立重建缓存")
            if adjusted and not old.empty:
                # 最后一根可能是未收盘日/周/月，变化不作为复权证据。
                overlap = old.iloc[:-1].merge(df, on="date", suffixes=("_old", "_new"))
                changed = any(not np.allclose(overlap[f"{c}_old"], overlap[f"{c}_new"], rtol=1e-5, atol=1e-4)
                              for c in ("open", "high", "low", "close")) if len(overlap) else False
                disjoint = old["date"].max() < df["date"].min() or df["date"].max() < old["date"].min()
                reset = reset or changed or disjoint
            if reset:
                # 备份不被行情扫描加载，可供人工核对/恢复；只保留最近一次重建前版本。
                with atomicFile(path.with_suffix(".parquet.bak")) as backup:
                    shutil.copyfile(path, backup)
                df.attrs["historyNotice"] = "历史数据口径已重建，旧数据已备份；当前历史范围以数据源返回窗口为准"
            else:
                attrs = {**old.attrs, **df.attrs}
                df = pd.concat([old, df]).drop_duplicates(subset="date", keep="last")
                df.attrs = attrs
        df = df.sort_values("date").reset_index(drop=True)
        with atomicFile(path) as temporary:
            df.to_parquet(temporary, index=False)
    return path


def loadBars(market: str, symbol: str, period: str = "day", dataDir: Path | None = None) -> pd.DataFrame | None:
    path = _barPath(market, symbol, period, dataDir)
    return pd.read_parquet(path) if path.exists() else None


def listSymbols(dataDir: Path | None = None) -> list[dict]:
    root = dataDir or DATA_DIR
    result = []
    if not root.exists():
        return result
    for marketDir in sorted(p for p in root.iterdir() if p.is_dir() and p.name in ("cn", "hk", "us")):
        for file in sorted(marketDir.glob("*.parquet")):
            if file.stem.endswith((".week", ".month")):
                continue
            df = pd.read_parquet(file, columns=["date"])
            result.append({"market": marketDir.name, "symbol": file.stem, "rows": len(df),
                           "dataInfo": df.attrs.get(META_KEY),
                           "startDate": str(df["date"].min().date()) if len(df) else None,
                           "endDate": str(df["date"].max().date()) if len(df) else None})
    return result
