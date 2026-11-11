"""自选股清单存储:JSON 文件持久化,单文件单职责。"""
import json
from pathlib import Path

from app.core.config import DATA_DIR
from app.core.files import atomicFile, fileLock
from app.core.validation import validateSymbol
from app.backtest.strategies import getStrategy

DEFAULT_STRATEGY = "sma_cross"
DEFAULT_PARAMS: dict = {"fastWindow": 5, "slowWindow": 20}


def _watchlistPath(dataDir: Path | None = None) -> Path:
    root = dataDir or DATA_DIR
    root.mkdir(parents=True, exist_ok=True)
    return root / "watchlist.json"


def loadWatchlist(dataDir: Path | None = None) -> list[dict]:
    """读取全部自选股,文件不存在返回空列表。"""
    path = _watchlistPath(dataDir)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _save(items: list[dict], dataDir: Path | None = None) -> None:
    with atomicFile(_watchlistPath(dataDir)) as temporary:
        temporary.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def addWatchItem(
    market: str, symbol: str, name: str = "", dataDir: Path | None = None
) -> dict:
    """添加自选股,已存在则原样返回。默认绑定双均线策略。"""
    symbol = validateSymbol(market, symbol)
    with fileLock(_watchlistPath(dataDir)):
        items = loadWatchlist(dataDir)
        for item in items:
            if item["market"] == market and item["symbol"] == symbol:
                return item
        item = {
            "market": market,
            "symbol": symbol,
            "name": name or symbol,
            "strategy": DEFAULT_STRATEGY,
            "params": dict(DEFAULT_PARAMS),
        }
        items.append(item)
        _save(items, dataDir)
        return item


def updateWatchItem(
    market: str, symbol: str, strategy: str, params: dict, dataDir: Path | None = None
) -> dict | None:
    """更新某只股票绑定的策略与参数,不存在返回 None。"""
    symbol = validateSymbol(market, symbol)
    params = getStrategy(strategy, **params).params
    with fileLock(_watchlistPath(dataDir)):
        items = loadWatchlist(dataDir)
        for item in items:
            if item["market"] == market and item["symbol"] == symbol:
                item["strategy"] = strategy
                item["params"] = params
                _save(items, dataDir)
                return item
        return None


def removeWatchItem(market: str, symbol: str, dataDir: Path | None = None) -> bool:
    """删除自选股,返回是否删除成功。"""
    symbol = validateSymbol(market, symbol)
    with fileLock(_watchlistPath(dataDir)):
        items = loadWatchlist(dataDir)
        kept = [i for i in items if not (i["market"] == market and i["symbol"] == symbol)]
        if len(kept) == len(items):
            return False
        _save(kept, dataDir)
        return True


def getWatchItem(market: str, symbol: str, dataDir: Path | None = None) -> dict | None:
    """按市场+代码查找单只自选股。"""
    for item in loadWatchlist(dataDir):
        if item["market"] == market and item["symbol"] == symbol:
            return item
    return None
