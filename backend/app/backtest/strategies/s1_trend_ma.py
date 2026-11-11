"""S1 趋势票 5 日线操作法(简化二元版)。

来源:《交易策略整理(结构化规则版)》§S1 + §12 已确认参数。
完整版含减仓/接回等仓位分层,当前引擎为 0/1 二元持仓,故取核心进出规则:
- 入场:连续 N 日收盘价站上 MA5(企稳,§12.7:N=3,不要求 MA5 向上)
- 出场:收盘价跌破 MA20(§S1 分层止损:跌破 20 日线清仓)
"""
import pandas as pd

from app.backtest.strategies.base import Strategy


class S1TrendMaStrategy(Strategy):
    name = "s1_trend_ma"
    label = "S1 趋势票5日线"
    desc = "趋势票核心策略:企稳(连续N日站上5日线)入场,跌破20日线清仓"
    paramsSchema = {
        "stableDays": {
            "type": "int",
            "default": 3,
            "min": 2,
            "max": 10,
            "desc": "企稳天数(连续站上5日线)",
        },
        "exitMa": {
            "type": "int",
            "default": 20,
            "min": 5,
            "max": 60,
            "desc": "清仓均线(跌破离场)",
        },
    }

    def generateSignals(self, bars: pd.DataFrame) -> pd.Series:
        stableDays = int(self.params.get("stableDays", 3))
        exitMaWindow = int(self.params.get("exitMa", 20))
        close = bars["close"]
        ma5 = close.rolling(5).mean()
        maExit = close.rolling(exitMaWindow).mean()

        # 企稳:连续 stableDays 日收盘价 > MA5(MA5 缺失的首段视为不满足)
        aboveMa5 = (close > ma5).fillna(False)
        stable = aboveMa5.rolling(stableDays).sum().fillna(0) >= stableDays

        # 状态机:企稳入场,收盘跌破清仓线离场
        signals: list[int] = []
        position = 0
        for i in range(len(bars)):
            if position == 0 and bool(stable.iloc[i]):
                position = 1
            elif position == 1 and pd.notna(maExit.iloc[i]) and close.iloc[i] < maExit.iloc[i]:
                position = 0
            signals.append(position)

        return pd.Series(signals, index=bars["date"].values)
