"""第三方接入的唯一管理文件：配置、默认源、外部HTTP/SDK调用均集中于此。

修改本文件后重启后端。SDK内部管理的HTTP地址标记为sdkManaged，不能只修改说明地址。
密钥应使用环境变量引用，禁止写入此文件；当前接口均不需要个人令牌。
"""
import importlib
import io
import multiprocessing
import os
from contextlib import redirect_stdout
from datetime import date, timedelta
from threading import RLock
from urllib.request import getproxies

import httpx
import pandas as pd

from app.core.validation import cnFullCode

DEFAULT_PROVIDERS = {
    "history": {"cn": "tencent", "hk": "tencent", "us": "yahoo"},
    "quotes": {"cn": "tencent", "hk": "tencent"},
    "minute": {"cn": "tencent", "hk": "tencent"},
}

# 自定义地址、超时、SDK函数名、参数名/字段映射、周期/复权映射，都在本文件维护。
PROVIDERS = {
    "tencent": {
        "label": "腾讯", "operations": ["history", "quotes", "minute"], "driver": "tencent", "enabled": True, "markets": ["cn", "hk"],
        "periods": ["day", "week", "month"], "adjustments": ["none", "qfq", "hfq"],
        "defaultAdjustment": "qfq", "maxBars": 640, "encoding": "gbk",
        "barFields": {"date": 0, "open": 1, "close": 2, "high": 3, "low": 4, "volume": 5},
        "quoteFields": {"name": 1, "price": 3, "prevClose": 4, "open": 5, "volume": 6,
                        "time": 30, "change": 31, "changePct": 32, "high": 33, "low": 34,
                        "amount": 37, "turnoverRate": 38, "peRatio": 39, "amplitude": 43,
                        "circulatingMarketCap": 44, "totalMarketCap": 45, "pbRatio": 46},
        "quoteCodeField": 2, "quoteScales": {"amount": 10000, "changePct": 0.01},
        "minuteFields": {"time": 0, "price": 1, "volume": 2, "amount": 3},
        "minuteCloseTimes": {"cn": "15:00", "hk": "16:00"},
        "urls": {"history": "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                 "minute": "https://web.ifzq.gtimg.cn/appstock/app/minute/query",
                 "quotes": "https://qt.gtimg.cn/q="},
        "timeouts": {"history": 30, "minute": 15, "quotes": 10},
        "volumeUnits": {"cn": "lot100", "hk": "share"},
    },
    "yahoo": {
        "label": "Yahoo / yfinance", "operations": ["history"], "driver": "yahoo", "enabled": True, "markets": ["us"],
        "periods": ["day", "week", "month"], "adjustments": ["none", "yahoo_auto_adjust"],
        "defaultAdjustment": "yahoo_auto_adjust", "sdk": "yfinance", "sdkManaged": True,
        "factory": "Ticker", "method": "history", "timeout": 20,
        "periodMap": {"day": "1d", "week": "1wk", "month": "1mo"},
        "columns": {"Date": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"},
        "volumeUnits": {"us": "share"},
    },
    "akshare": {
        "label": "AKShare（东方财富）", "operations": ["history"], "driver": "sdk", "request": "akshare", "exchanges": ["sh", "sz"], "enabled": True, "markets": ["cn", "hk"],
        "periods": ["day", "week", "month"], "adjustments": ["none", "qfq", "hfq"],
        "defaultAdjustment": "qfq", "sdk": "akshare", "sdkManaged": True, "timeout": 20,
        "source": "eastmoney",  # 底层来源，不把AKShare库名当作独立数据源。
        "methods": {"cn_stock": "stock_zh_a_hist", "cn_index": "index_zh_a_hist", "hk_stock": "stock_hk_hist"},
        "params": {"symbol": "symbol", "period": "period", "startDate": "start_date", "endDate": "end_date", "adjustment": "adjust"},
        "periodMap": {"day": "daily", "week": "weekly", "month": "monthly"},
        "adjustmentMap": {"none": "", "qfq": "qfq", "hfq": "hfq"},
        "columns": {"日期": "date", "开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量": "volume"},
        "volumeUnits": {"cn": "lot100", "hk": "share"},
        "networkHosts": ["push2his.eastmoney.com", "33.push2his.eastmoney.com", "*.push2.eastmoney.com"],
    },
    "baostock": {
        "label": "BaoStock", "operations": ["history"], "driver": "sdk", "request": "baostock", "exchanges": ["sh", "sz"], "enabled": True, "markets": ["cn"],
        "periods": ["day", "week", "month"], "adjustments": ["none", "qfq", "hfq"],
        "defaultAdjustment": "qfq", "sdk": "baostock", "timeout": 15, "requestTimeout": 40,
        "host": "public-api.baostock.com", "port": 10030, "transport": "tcp",
        "loginMethod": "login", "queryMethod": "query_history_k_data_plus", "logoutMethod": "logout",
        "excludeRows": {"field": "tradestatus", "value": "0", "countField": "excludedSuspendedRows"},
        "fields": "date,code,open,high,low,close,volume",
        "dailyStockFields": "date,code,open,high,low,close,volume,tradestatus", "maxRows": 100000,
        "periodMap": {"day": "d", "week": "w", "month": "m"},
        "adjustmentMap": {"none": "3", "qfq": "2", "hfq": "1"},
        "columns": {"date": "date", "open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"},
        "volumeUnits": {"cn": "share"},
    },
}
class DataSourceRequestError(ValueError):
    """明确不支持的调用参数，与上游数据/网络故障区分。"""


_akLock = RLock()


def providerSettings(name: str) -> dict:
    if name not in PROVIDERS:
        raise ValueError(f"未知数据源: {name}")
    settings = PROVIDERS[name]
    if not settings["enabled"]:
        raise ValueError(f"数据源已停用: {name}")
    return settings


def makeProvider(market: str, source: str | None = None, adjustment: str | None = None, operation: str = "history"):
    from app.data.tencent_provider import TencentProvider
    from app.data.yfinance_provider import YFinanceProvider
    from app.data.sdk_provider import SDKProvider
    source = source or DEFAULT_PROVIDERS.get(operation, {}).get(market)
    if source is None:
        raise ValueError(f"{market} 暂无 {operation} 数据源")
    settings = providerSettings(source)
    if operation not in settings["operations"]:
        raise ValueError(f"{source}未接入{operation}能力")
    if market not in settings["markets"]:
        raise ValueError(f"{source} 不支持 {market} 市场")
    if adjustment is not None and adjustment not in settings["adjustments"]:
        raise ValueError(f"{source} 不支持复权方式 {adjustment}")
    driver = settings["driver"]
    if driver == "tencent": return TencentProvider(market, adjustment)
    if driver == "yahoo": return YFinanceProvider(adjustment)
    if driver == "sdk": return SDKProvider(market, source, adjustment)
    raise ValueError(f"未配置数据源驱动: {source}")


def listProviders() -> list[dict]:
    # 只返回产品需要的能力信息，凭据/内部连接配置不暴露到前端。
    return [{"id": key, "label": value["label"], "enabled": value["enabled"],
             "markets": value["markets"], "periods": value["periods"], "operations": value["operations"],
             "adjustments": value["adjustments"], "defaultAdjustment": value["defaultAdjustment"]}
            for key, value in PROVIDERS.items()]


def tencentRequest(operation: str, *, params: dict | None = None, codes: list[str] | None = None):
    settings = providerSettings("tencent")
    url = settings["urls"][operation]
    if operation == "quotes": url += ",".join(codes or [])
    with httpx.Client(trust_env=True, timeout=settings["timeouts"][operation]) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        return response.content.decode(settings["encoding"], errors="strict") if operation == "quotes" else response.json()


def tencentHistory(code: str, startDate: str, endDate: str, period: str, adjustment: str):
    settings = providerSettings("tencent")
    dates = f"{startDate},{endDate}" if period == "day" else ","
    adjust = adjustment if adjustment != "none" else ""
    param = f"{code},{period},{dates},{settings['maxBars']},{adjust}"
    return tencentRequest("history", params={"param": param})


def tencentMinute(code: str):
    return tencentRequest("minute", params={"code": code})


def ensureYahooProxy() -> None:
    if os.environ.get("HTTPS_PROXY"): return
    proxy = os.environ.get("QUANT_PROXY") or getproxies().get("https") or getproxies().get("http")
    if proxy:
        os.environ["HTTPS_PROXY"] = proxy
        os.environ["HTTP_PROXY"] = proxy


def yahooHistory(symbol: str, startDate: str, endDate: str, period: str, adjustment: str) -> pd.DataFrame:
    ensureYahooProxy()
    settings = providerSettings("yahoo")
    sdk = importlib.import_module(settings["sdk"])
    ticker = getattr(sdk, settings["factory"])(symbol)
    return getattr(ticker, settings["method"])(
        start=startDate, end=(date.fromisoformat(endDate) + timedelta(days=1)).isoformat(),
        interval=settings["periodMap"][period], auto_adjust=adjustment == "yahoo_auto_adjust",
        raise_errors=True, timeout=settings["timeout"],
    )


def akshareHistory(market: str, symbol: str, kind: str, startDate: str, endDate: str,
                   period: str, adjustment: str, *, settings: dict | None = None) -> pd.DataFrame:
    settings = settings or providerSettings("akshare")
    sdk = importlib.import_module(settings["sdk"])
    key = f"{market}_{kind}"
    if key not in settings["methods"]:
        raise ValueError(f"AKShare未配置{market}/{kind}接口")
    values = {"symbol": cnFullCode(symbol)[2:] if market == "cn" else symbol,
              "period": settings["periodMap"][period], "startDate": startDate.replace("-", ""),
              "endDate": endDate.replace("-", ""), "adjustment": settings["adjustmentMap"][adjustment]}
    if kind == "index": values.pop("adjustment")
    params = {settings["params"][key]: value for key, value in values.items()}
    # AKShare网络设置是SDK全局状态，锁住临时设置及调用后恢复；代理保持环境继承。
    with _akLock:
        previous = sdk.get_timeout()
        try:
            sdk.set_timeout(settings["timeout"])
            return getattr(sdk, settings["methods"][key])(**params)
        finally:
            sdk.set_timeout(previous)


def requestSDKHistory(source: str, market: str, symbol: str, kind: str, startDate: str, endDate: str,
                      period: str, adjustment: str) -> pd.DataFrame:
    settings = providerSettings(source)
    handler = settings["request"]
    if handler == "akshare": return akshareHistory(market, symbol, kind, startDate, endDate, period, adjustment, settings=settings)
    if handler == "baostock": return baostockHistory(symbol, startDate, endDate, period, adjustment, settings=settings)
    raise ValueError(f"SDK调用未实现: {handler}")


def runBaostock(settings: dict, symbol: str, startDate: str, endDate: str, period: str, adjustment: str) -> pd.DataFrame:
    """在独立进程内运行，隔离BaoStock全局登录会话及TCP超时配置。"""
    import socket
    sdk = importlib.import_module(settings["sdk"])
    constants = importlib.import_module(settings["sdk"] + ".common.contants")
    constants.BAOSTOCK_SERVER_IP = settings["host"]
    constants.BAOSTOCK_SERVER_PORT = settings["port"]
    previousTimeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(settings["timeout"])
    connected = False
    try:
        login = getattr(sdk, settings["loginMethod"])()
        if login is None or login.error_code != "0":
            raise RuntimeError(f"BaoStock登录失败: {getattr(login, 'error_msg', '无响应')}")
        connected = True
        code = cnFullCode(symbol)
        code = code[:2] + "." + code[2:]
        from app.data.contract import instrument
        fields = settings["dailyStockFields"] if period == "day" and instrument("cn", symbol)["instrumentType"] == "stock" else settings["fields"]
        result = getattr(sdk, settings["queryMethod"])(
            code, fields, start_date=startDate, end_date=endDate,
            frequency=settings["periodMap"][period], adjustflag=settings["adjustmentMap"][adjustment],
        )
        if result is None or result.error_code != "0":
            raise RuntimeError(f"BaoStock查询失败: {getattr(result, 'error_msg', '无响应')}")
        rows = []
        while result.next():
            if result.error_code != "0": raise RuntimeError(f"BaoStock分页失败: {result.error_msg}")
            rows.append(result.get_row_data())
            if len(rows) > settings["maxRows"]: raise RuntimeError("BaoStock返回数据超过安全行数上限")
        if result.error_code != "0": raise RuntimeError(f"BaoStock分页失败: {result.error_msg}")
        frame = pd.DataFrame(rows, columns=result.fields)
        if not frame.empty and not frame["code"].eq(code).all():
            raise RuntimeError("BaoStock返回了其他标的的数据")
        return frame
    finally:
        if connected:
            try: getattr(sdk, settings["logoutMethod"])()
            except Exception: pass
        socket.setdefaulttimeout(previousTimeout)


def _baostockWorker(connection, settings, args):
    try:
        with redirect_stdout(io.StringIO()):
            frame = runBaostock(settings, *args)
        connection.send((True, frame))
    except Exception as exc:
        connection.send((False, str(exc)))
    finally:
        connection.close()


def baostockHistory(symbol: str, startDate: str, endDate: str, period: str, adjustment: str, *, settings: dict | None = None) -> pd.DataFrame:
    settings = settings or providerSettings("baostock")
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_baostockWorker, args=(sender, settings, (symbol, startDate, endDate, period, adjustment)))
    try:
        process.start()
        sender.close()
        if not receiver.poll(settings["requestTimeout"]):
            raise TimeoutError("BaoStock请求超时，请检查TCP网络连接")
        try: success, payload = receiver.recv()
        except EOFError as exc: raise RuntimeError("BaoStock数据进程异常退出") from exc
        if not success: raise RuntimeError(payload)
        return payload
    finally:
        receiver.close()
        sender.close()
        if process.pid is not None:
            if process.is_alive(): process.terminate()
            process.join(timeout=2)
            if process.is_alive(): process.kill(); process.join()
