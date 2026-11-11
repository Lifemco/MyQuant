"""共享的市场/代码校验，所有磁盘与 API 入口均使用同一规则。"""
import re


def validateSymbol(market: str, symbol: str) -> str:
    patterns = {"cn": r"\d{6}", "hk": r"\d{5}", "us": r"[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)*"}
    symbol = symbol.strip().upper()
    if market not in patterns or len(symbol) > 20 or not re.fullmatch(patterns[market], symbol):
        raise ValueError("市场或股票代码无效：A股为6位、港股为5位，美股使用字母数字及点/连字符")
    return symbol
