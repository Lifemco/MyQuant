import json
from datetime import datetime, timezone
from uuid import uuid4

import pandas as pd

from app.core.config import DATA_DIR
from app.core.files import atomicFile, fileLock
from app.core.validation import validateSymbol
from app.strategies.models import FactorUpload, SaveStrategy

STRATEGY_DIR = DATA_DIR / "strategies"


class VersionConflict(ValueError):
    pass


def listSaved() -> list[dict]:
    path = STRATEGY_DIR / "library.json"
    return json.loads(path.read_text()) if path.exists() else []


def saveStrategy(request: SaveStrategy) -> dict:
    path = STRATEGY_DIR / "library.json"
    with fileLock(path):
        items = listSaved()
        current = next((item for item in items if item["id"] == request.id), None)
        if request.id and current is None:
            raise ValueError("保存的策略不存在，请另存为新策略")
        if current and current["version"] != request.version:
            raise VersionConflict("策略已在其他页面更新，请重新加载后编辑")
        if not current and len(items) >= 1000:
            raise ValueError("策略库最多保存1000条")
        stamp = datetime.now(timezone.utc).isoformat()
        item = {"id": request.id or uuid4().hex, "version": (current["version"] if current else 0) + 1,
                "spec": request.spec.model_dump(), "prompt": request.prompt, "summary": request.summary,
                "createdAt": current["createdAt"] if current else stamp, "updatedAt": stamp}
        items = [old for old in items if old["id"] != item["id"]] + [item]
        with atomicFile(path) as temp:
            temp.write_text(json.dumps(items, ensure_ascii=False, allow_nan=False))
        return item


def _factorPath(market, symbol, factor):
    # factor名称由Pydantic与此处共同约束，禁止路径输入。
    import re
    symbol = validateSymbol(market, symbol)
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", factor):
        raise ValueError("因子名称无效")
    root = STRATEGY_DIR.resolve()
    path = (root / "factors" / market / symbol / f"{factor}.parquet").resolve()
    if not path.is_relative_to(root):
        raise ValueError("因子路径超出数据目录")
    return path


def saveFactor(request: FactorUpload) -> dict:
    path = _factorPath(request.market, request.symbol, request.factor)
    rows = pd.DataFrame([item.model_dump() for item in request.observations])
    rows["availableAt"] = pd.to_datetime(rows.availableAt, utc=True)
    if rows.availableAt.duplicated().any():
        raise ValueError("因子发布时间重复；请提供每个时点唯一的已知值")
    rows = rows.sort_values("availableAt")
    rows.attrs.update(source=request.source, factor=request.factor, market=request.market, symbol=request.symbol)
    with fileLock(path):
        with atomicFile(path) as temp:
            rows.to_parquet(temp, index=False)
    return {"factor": request.factor, "market": request.market, "symbol": request.symbol,
            "source": request.source, "rows": len(rows)}


def loadFactor(market, symbol, factor):
    path = _factorPath(market, symbol, factor)
    if not path.exists():
        raise ValueError(f"缺少外部因子 {factor}：请先导入 {market}/{symbol} 的发布时间和值")
    return pd.read_parquet(path)


def listFactors() -> list[dict]:
    folder = STRATEGY_DIR / "factors"
    result = []
    for path in sorted(folder.glob("*/*/*.parquet")):
        rows = pd.read_parquet(path)
        result.append({"factor": path.stem, "market": path.parent.parent.name, "symbol": path.parent.name,
                       "source": rows.attrs.get("source", "用户导入"), "rows": len(rows)})
    return result
