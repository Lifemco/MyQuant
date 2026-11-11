"""信号监控服务:在最新行情上运行策略,产出买卖点标记与当前持仓状态。

与回测引擎口径一致:信号在 T 日收盘产生,T+1 执行;
但监控提示展示的是 T 日的信号本身(用户次日开盘手动操作)。
"""
import pandas as pd

from app.backtest.strategies.base import Strategy


def computeSignalMarkers(bars: pd.DataFrame, strategy: Strategy) -> dict:
    """计算买卖点标记序列与当前状态。

    Returns:
        markers: [{date, type: buy/sell, price}],按时间升序
        holding: 当前是否应持仓(最新信号为 1)
        lastSignal: 最近一次买卖点(无则 None)
        positionSeries: 每日目标持仓(0/1),供前端绘制持仓区间
    """
    df = bars.sort_values("date").reset_index(drop=True)
    signals = strategy.generateSignals(df).reindex(df["date"].values).fillna(0).astype(int)

    closes = df.set_index(pd.DatetimeIndex(df["date"]))["close"]
    markers: list[dict] = []
    prev = 0
    for date, sig in signals.items():
        ts = pd.Timestamp(date)
        if prev == 0 and sig == 1:
            markers.append(
                {"date": str(ts.date()), "type": "buy", "price": round(float(closes.loc[ts]), 4)}
            )
        elif prev == 1 and sig == 0:
            markers.append(
                {"date": str(ts.date()), "type": "sell", "price": round(float(closes.loc[ts]), 4)}
            )
        prev = int(sig)

    holding = bool(signals.iloc[-1] == 1) if len(signals) else False
    return {
        "markers": markers,
        "holding": holding,
        "lastSignal": markers[-1] if markers else None,
    }


def summarizeBars(bars: pd.DataFrame) -> dict:
    """提取最新收盘价与涨跌幅,供列表展示。"""
    if bars.empty:
        return {"close": None, "changePct": None}
    close = float(bars.iloc[-1]["close"])
    changePct = None
    if len(bars) >= 2 and bars.iloc[-2]["close"]:
        changePct = round(close / float(bars.iloc[-2]["close"]) - 1, 4)
    return {"close": round(close, 4), "changePct": changePct}
