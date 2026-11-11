"""共享的市场/代码校验，所有磁盘与 API 入口均使用同一规则。"""
import re


def validateSymbol(market: str, symbol: str) -> str:
    patterns = {"cn": r"(?:(?:SH|SZ|BJ))?\d{6}", "hk": r"\d{5}", "us": r"[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)*"}
    symbol = symbol.strip().upper()
    if market not in patterns or len(symbol) > 20 or not re.fullmatch(patterns[market], symbol):
        raise ValueError("市场或股票代码无效：A股为6位、港股为5位，美股使用字母数字及点/连字符")
    if market == "cn":
        code = cnFullCode(symbol)
        # 常见指数必须保留交易所；sh000001与sz000001是不同标的。
        if code.startswith(("sh000", "sz399", "bj899")):
            return code
        inferred = cnFullCode(code[2:])
        if code != inferred:
            raise ValueError("股票代码与交易所前缀不匹配")
        return code[2:]
    return symbol


def cnFullCode(symbol: str) -> str:
    value = symbol.lower()
    if value.startswith(("sh", "sz", "bj")):
        return value
    prefix = "bj" if value.startswith(("4", "8", "920")) else "sh" if value.startswith(("6", "9")) else "sz"
    return prefix + value
