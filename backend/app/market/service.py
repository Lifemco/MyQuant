"""市场总览：独立缓存、后台采集、明确来源与样本分母。"""
import fcntl
import json
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.core.config import DATA_DIR
from app.core.files import atomicFile, fileLock
from app.data import third_party
from app.data.contract import validateBars
from app.monitor.session import closedBars

MARKET_DIR = DATA_DIR / "market"
SECTION_NAMES = ("trend", "industry", "distribution", "breadth", "style", "valuation")
CN = ZoneInfo("Asia/Shanghai")


def now() -> datetime:
    return datetime.now(CN)


def _read() -> dict:
    path = MARKET_DIR / "overview.json"
    if not path.exists():
        return {"sections": {}, "job": {"running": False}}
    return json.loads(path.read_text())


def _write(**updates) -> None:
    path = MARKET_DIR / "overview.json"
    with fileLock(path):
        content = _read()
        if "section" in updates:
            key, value = updates.pop("section")
            content["sections"][key] = value
        content.update(updates)
        with atomicFile(path) as temp:
            temp.write_text(json.dumps(content, ensure_ascii=False, allow_nan=False))


def _jobActive() -> bool:
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    with (MARKET_DIR / "collection.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
        return False


def overview() -> dict:
    content = _read()
    active = _jobActive()
    if content["job"].get("running") and not active:
        content["job"].update(running=False, error="采集进程已停止；可重新刷新，宽度任务会复用当日成功缓存。")
    for key in SECTION_NAMES:
        section = content["sections"].setdefault(key, {
            "status": "unavailable", "source": "尚未采集", "asOf": None,
            "fetchedAt": None, "notes": "点击刷新市场数据；宽度图需单独构建。", "data": None,
        })
        stamp = section.get("fetchedAt")
        if stamp and now() - datetime.fromisoformat(stamp) > timedelta(hours=24) and section["data"] is not None:
            section["status"] = "stale"
        if section.get("asOf") and (now().date() - datetime.fromisoformat(section["asOf"]).date()).days > 7:
            section["status"] = "stale"
    return content


def _numeric(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    frame = frame.copy()
    for key in columns:
        frame[key] = pd.to_numeric(frame[key], errors="coerce").replace([np.inf, -np.inf], np.nan)
    return frame


def distribution(frame: pd.DataFrame) -> dict:
    """百分点分箱；缺价、停牌/零成交、缺涨跌幅排除，0%属于[-1,1)。"""
    if frame["symbol"].duplicated().any():
        raise ValueError("全市场快照存在重复证券代码")
    rows = _numeric(frame, ["close", "change", "amount"])
    valid = rows.loc[(rows.close > 0) & (rows.amount > 0) & rows.change.notna(), "change"]
    if valid.empty:
        raise ValueError("全市场快照没有有效交易样本")
    edges = [-np.inf, -10, -7, -5, -3, -1, 1, 3, 5, 7, 10, np.inf]
    counts = pd.cut(valid, edges, right=False).value_counts(sort=False)
    labels = ["<-10", "[-10,-7)", "[-7,-5)", "[-5,-3)", "[-3,-1)", "[-1,1)", "[1,3)", "[3,5)", "[5,7)", "[7,10)", "≥10"]
    return {"bins": [{"label": label, "count": int(count)} for label, count in zip(labels, counts)],
            "total": len(rows), "valid": len(valid), "excluded": len(rows) - len(valid),
            "up": int((valid > 0).sum()), "flat": int((valid == 0).sum()), "down": int((valid < 0).sum())}


def indexHistory(frame: pd.DataFrame) -> pd.DataFrame:
    rows = _numeric(frame, ["close", "amount"])
    rows["date"] = pd.to_datetime(rows.date, errors="raise").dt.normalize()
    if rows.date.duplicated().any() or rows[["close", "amount"]].isna().any().any() or (rows.close <= 0).any() or (rows.amount < 0).any():
        raise ValueError("指数历史字段无效")
    return closedBars(rows.sort_values("date"), "cn").tail(120)


def relativePerformance(histories: dict[str, pd.DataFrame]) -> dict:
    """所有序列使用相同交易日和基日，缺少任一序列则不构造比较。"""
    if len(histories) < 2:
        raise ValueError("风格对比至少需要两条序列")
    aligned = pd.concat({name: frame.set_index("date").close for name, frame in histories.items()}, axis=1).dropna().sort_index()
    if len(aligned) < 2:
        raise ValueError("风格指数没有足够共同交易日")
    normalized = aligned.div(aligned.iloc[0]).mul(100)
    return {"baseDate": aligned.index[0].date().isoformat(),
            "dates": [d.date().isoformat() for d in aligned.index],
            "series": [{"name": name, "values": values.tolist()} for name, values in normalized.items()]}


def valuation(frame: pd.DataFrame) -> dict:
    rows = _numeric(frame, ["pe"])
    rows["date"] = pd.to_datetime(rows.date, errors="raise").dt.normalize()
    rows = closedBars(rows.sort_values("date"), "cn")
    if rows.date.duplicated().any():
        raise ValueError("估值日期重复")
    rows = rows.loc[(rows.pe > 0) & rows.pe.notna()]
    if rows.empty:
        raise ValueError("没有有效正PE样本")
    # 每一点只使用当时及以前5年数据；并列值使用中位秩，避免前视。
    records = []
    for row in rows.itertuples():
        window = rows.loc[(rows.date > row.date - pd.DateOffset(years=5)) & (rows.date <= row.date), "pe"]
        percentile = ((window < row.pe).sum() + 0.5 * (window == row.pe).sum()) / len(window) * 100
        records.append({"date": row.date.date().isoformat(), "pe": float(row.pe), "percentile": float(percentile), "samples": len(window)})
    return {"name": "沪深300", "metric": "滚动市盈率 PE-TTM", "points": records[-120:]}


def _breadthCounts(histories: dict[str, pd.DataFrame]) -> dict:
    """分母按每日有效历史长度分别计算；严格站上，不把相等计入。"""
    aggregate: dict = {}
    for frame in histories.values():
        rows = closedBars(validateBars(frame), "cn")
        rows = rows.loc[rows.volume > 0].copy()
        for window in (20, 60):
            mean = rows.close.rolling(window, min_periods=window).mean()
            for date, close, ma in zip(rows.date, rows.close, mean):
                if pd.isna(ma):
                    continue
                key = date.date().isoformat()
                point = aggregate.setdefault(key, {"date": key, "eligible20": 0, "above20": 0, "eligible60": 0, "above60": 0})
                point[f"eligible{window}"] += 1
                point[f"above{window}"] += int(close > ma)
    return aggregate


def _breadthData(aggregate: dict, total: int, collected: int) -> dict:
    points = []
    for key in sorted(aggregate)[-120:]:
        point = aggregate[key].copy()
        for window in (20, 60):
            n = point[f"eligible{window}"]
            point[f"ma{window}"] = point[f"above{window}"] / n * 100 if n else None
        points.append(point)
    return {"total": total, "collected": collected, "points": points}


def breadth(histories: dict[str, pd.DataFrame], total: int) -> dict:
    return _breadthData(_breadthCounts(histories), total, len(histories))


def _section(key: str, data: dict | list, source: str, notes: str, asOf=None, partial=False):
    _write(section=(key, {"status": "partial" if partial else "ok", "data": data, "source": source,
                          "notes": notes, "asOf": asOf, "fetchedAt": now().isoformat(), "error": None}))


def _failed(key: str, exc: Exception):
    # 不把可能含令牌的第三方URL/请求参数返回浏览器。
    old = _read()["sections"].get(key)
    if old and old.get("data") is not None:
        old.update(status="stale", error=f"本次采集失败（{type(exc).__name__}），保留上次成功数据。")
    else:
        operation = {"trend": "index", "style": "index", "distribution": "spot", "breadth": "index"}.get(key, key)
        source = (third_party.MARKET_OVERVIEW["breadth"]["source"] if key == "breadth"
                  else third_party.MARKET_OVERVIEW["calls"][operation]["source"])
        old = {"status": "unavailable", "data": None, "source": source, "asOf": None,
               "fetchedAt": None, "notes": "检查数据源网络连通性及第三方字段配置。", "error": f"采集失败（{type(exc).__name__}）"}
    _write(section=(key, old))


def _refresh():
    settings = third_party.MARKET_OVERVIEW
    histories = {}
    errors = []
    end = now().date()
    total = len(settings["indices"]) + 3
    for i, (code, name) in enumerate(settings["indices"].items()):
        try:
            rows = indexHistory(third_party.marketOverviewRequest("index", symbol=code, startDate=(end - timedelta(days=240)).isoformat(), endDate=end.isoformat()))
            if rows.empty:
                raise ValueError("没有收盘数据")
            histories[code] = rows
        except Exception:
            errors.append(name)
        _write(job={"running": True, "kind": "refresh", "done": i + 1, "total": total})
    try:
        series = [{"name": settings["indices"][code], "code": code,
                   "points": [{"date": row.date.date().isoformat(), "close": float(row.close), "amount": float(row.amount)} for row in histories[code].itertuples()]}
                  for code in settings["trendIndices"] if code in histories]
        if not series:
            raise ValueError("指数数据全部缺失")
        _section("trend", series, settings["calls"]["index"]["source"],
                 "收盘指数（点）与该指数成交额（元）；各指数成交额不可相加。缺失指数：" + ("、".join(errors) or "无"),
                 min(s["points"][-1]["date"] for s in series), len(series) < len(settings["trendIndices"]))
    except Exception as exc:
        _failed("trend", exc)
    try:
        selected = {settings["indices"][code]: histories[code] for code in settings["styleIndices"]}
        data = relativePerformance(selected)
        _section("style", data, settings["calls"]["index"]["source"],
                 "共同基日=100，价格指数，不含分红；沪深300/中证500/中证1000对比规模，沪深300成长/价值对比风格。", data["dates"][-1])
    except Exception as exc:
        _failed("style", exc)
    for operation in ("industry", "spot", "valuation"):
        key = "distribution" if operation == "spot" else operation
        try:
            frame = third_party.marketOverviewRequest(operation)
            if operation == "spot":
                frame["symbol"] = frame.symbol.astype(str).str.zfill(6)
                if not frame.symbol.str.fullmatch(r"[0-9]{6}").all():
                    raise ValueError("快照证券代码无效")
                data = distribution(frame)
                frame.attrs["observedAt"] = now().isoformat()
                with atomicFile(MARKET_DIR / "universe.parquet") as temp:
                    frame.to_parquet(temp, index=False)
                _section(key, data, settings["calls"][operation]["source"],
                         "沪深京A股最新快照，涨跌幅单位%；排除停牌/零成交和缺价样本。源未提供逐股时间戳，抓取时间不等于行情日期。", partial=True)
            elif operation == "industry":
                rows = _numeric(frame, ["change", "size"]).dropna()
                rows = rows.loc[rows["size"] > 0]
                if rows.empty or rows.symbol.duplicated().any():
                    raise ValueError("行业快照无效")
                _section(key, rows.to_dict("records"), settings["calls"][operation]["source"],
                         f"东方财富行业分类；面积=总市值（元），红涨绿跌。有效行业 {len(rows)}/{len(frame)}；源未提供行情日期。", partial=True)
            else:
                data = valuation(frame)
                _section(key, data, settings["calls"][operation]["source"],
                         "以沪深300代表大盘估值；PE-TTM近5年滚动历史分位（并列中位秩），仅正PE，窗口不足5年时使用已有样本。", data["points"][-1]["date"])
        except Exception as exc:
            _failed(key, exc)
        _write(job={"running": True, "kind": "refresh", "done": len(settings["indices"]) + 1 + ("industry", "spot", "valuation").index(operation), "total": total})


def _universe() -> pd.DataFrame:
    path = MARKET_DIR / "universe.parquet"
    if not path.exists():
        raise ValueError("请先刷新市场数据，获取全市场证券名单")
    universe = pd.read_parquet(path)
    stamp = universe.attrs.get("observedAt")
    if not stamp or now() - datetime.fromisoformat(stamp) > timedelta(hours=24):
        raise ValueError("全市场证券名单已过期，请先刷新市场数据")
    if universe.symbol.duplicated().any() or not universe.symbol.str.fullmatch(r"[0-9]{6}").all():
        raise ValueError("全市场证券名单代码无效")
    return universe


def _collectBreadth():
    universe = _universe()
    # 当前接入的历史接口仅验证沪深；北交所明确排除，不静默丢弃。
    symbols = universe.symbol.loc[universe.symbol.str.match(r"^[036]\d{5}$")].tolist()
    if not symbols:
        raise ValueError("缺少沪深A股全市场证券列表，请先刷新市场数据")
    target = now().date()
    if now().hour < 15:
        target -= timedelta(days=1)
    while target.weekday() > 4:
        target -= timedelta(days=1)
    folder = MARKET_DIR / "breadth-history"
    folder.mkdir(exist_ok=True)
    settings = third_party.MARKET_OVERVIEW["breadth"]
    identity = {"provider": settings["provider"], "adjustment": settings["adjustment"]}
    collected = 0
    aggregate = {}
    failed = consecutive = 0
    adjustLabel = {"qfq": "前复权", "hfq": "后复权", "none": "不复权"}[settings["adjustment"]]
    note = f"沪深A股名单抓取于{universe.attrs['observedAt']}（存在幸存者偏差），{adjustLabel}；MA基于有效成交日收盘价，停牌/不足20或60日分别排除。北交所未纳入。"
    for i, symbol in enumerate(symbols):
        path = folder / f"{symbol}.parquet"
        try:
            cached = pd.read_parquet(path) if path.exists() else None
            if cached is None or cached.attrs.get("target") != target.isoformat() or cached.attrs.get("collectionIdentity") != identity:
                provider = third_party.makeProvider("cn", settings["provider"], settings["adjustment"])
                cached = validateBars(provider.fetchDailyBars(symbol, (target - timedelta(days=450)).isoformat(), target.isoformat(), period="day"))
                if cached.empty:
                    raise ValueError("无历史数据")
                cached.attrs["target"] = target.isoformat()
                cached.attrs["collectionIdentity"] = identity
                with atomicFile(path) as temp:
                    cached.to_parquet(temp, index=False)
            cached = validateBars(cached)
            for key, counts in _breadthCounts({symbol: cached}).items():
                point = aggregate.setdefault(key, {"date": key, "eligible20": 0, "above20": 0, "eligible60": 0, "above60": 0})
                for field in ("eligible20", "above20", "eligible60", "above60"):
                    point[field] += counts[field]
            collected += 1
            consecutive = 0
        except Exception:
            failed += 1
            consecutive += 1
        if (i + 1) % 25 == 0 or i + 1 == len(symbols) or consecutive >= 5:
            data = _breadthData(aggregate, len(symbols), collected)
            data.update(failed=failed, processed=i + 1)
            if data["points"]:
                _section("breadth", data, settings["source"], note + f" 已采集 {collected}/{len(symbols)}，失败 {failed}；历史每日有效分母见提示。",
                         data["points"][-1]["date"], partial=collected < len(symbols))
            _write(job={"running": True, "kind": "breadth", "done": i + 1, "total": len(symbols), "failed": failed})
        if consecutive >= 5:
            raise RuntimeError("连续5只股票采集失败，已停止；检查网络后重试")
    if not aggregate:
        raise ValueError("未获得任何有效个股历史数据")


def _run(kind: str, lock):
    error = None
    try:
        _collectBreadth() if kind == "breadth" else _refresh()
    except Exception as exc:
        error = "采集任务中止，请检查网络后重试；成功缓存已保留。" + f"（{type(exc).__name__}）"
        if kind == "breadth":
            _failed("breadth", exc)
    finally:
        job = _read()["job"]
        job.update(running=False, kind=kind, error=error)
        _write(job=job)
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def startCollection(kind: str = "refresh") -> dict:
    if kind not in ("refresh", "breadth"):
        raise ValueError("未知采集任务")
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    if kind == "breadth":
        _universe()
    lock = (MARKET_DIR / "collection.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return overview()
    try:
        _write(job={"running": True, "kind": kind, "done": 0, "total": 0, "error": None})
        Thread(target=_run, args=(kind, lock), daemon=True).start()
    except Exception:
        lock.close()
        raise
    return overview()
