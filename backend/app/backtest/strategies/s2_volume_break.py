"""S2 放量突破加仓策略(简化二元版)。

来源:《交易策略整理(结构化规则版)》§S2 + §10 量能标准 + §12.3 已确认参数。
- 入场:收盘价突破前 N 日最高价(不含当日),且满足双量能条件:
  ① 当日量 ≥ 前一日量 × volRatioMin(放量)
  ② 当日量 > 前 5 日均量 × volMaMultiple
- 出场:收盘价跌破 MA10(趋势生命线)

注:日线级别用"当日量/前一日量"近似量比(量比严格定义为分钟均量口径)。
"""
import pandas as pd

from app.backtest.strategies.base import Strategy


class S2VolumeBreakStrategy(Strategy):
    name = "s2_volume_break"
    label = "S2 放量突破"
    desc = "放量突破 N 日前高入场(双量能条件确认),跌破 10 日线离场"
    paramsSchema = {
        "breakWindow": {
            "type": "int",
            "default": 20,
            "min": 5,
            "max": 120,
            "desc": "压力位窗口(N 日前高)",
        },
        "volRatioMin": {
            "type": "float",
            "default": 1.5,
            "min": 1.0,
            "max": 5.0,
            "desc": "放量倍数(当日量/前日量)",
        },
        "volMaMultiple": {
            "type": "float",
            "default": 1.5,
            "min": 1.0,
            "max": 5.0,
            "desc": "量能均线倍数(当日量/5日均量)",
        },
        "exitMa": {
            "type": "int",
            "default": 10,
            "min": 5,
            "max": 60,
            "desc": "离场均线(跌破离场)",
        },
    }

    def generateSignals(self, bars: pd.DataFrame) -> pd.Series:
        window = int(self.params.get("breakWindow", 20))
        volRatioMin = float(self.params.get("volRatioMin", 1.5))
        volMaMultiple = float(self.params.get("volMaMultiple", 1.5))
        exitMaWindow = int(self.params.get("exitMa", 10))

        close = bars["close"]
        volume = bars["volume"]

        # 压力位:前 N 日最高价(不含当日,避免当日自身参与)
        resistance = bars["high"].shift(1).rolling(window).max()
        breakout = close > resistance

        # 双量能条件(首日/均线缺失段视为不满足)
        volUp = (volume / volume.shift(1) >= volRatioMin).fillna(False)
        volStrong = (volume / volume.rolling(5).mean().shift(1) > volMaMultiple).fillna(False)
        entry = (breakout & volUp & volStrong).fillna(False)

        maExit = close.rolling(exitMaWindow).mean()

        signals: list[int] = []
        position = 0
        for i in range(len(bars)):
            if position == 0 and bool(entry.iloc[i]):
                position = 1
            elif position == 1 and pd.notna(maExit.iloc[i]) and close.iloc[i] < maExit.iloc[i]:
                position = 0
            signals.append(position)

        return pd.Series(signals, index=bars["date"].values)
