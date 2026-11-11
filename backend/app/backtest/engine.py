"""向量化回测引擎:T 日收盘出信号,T+1 日生效,扣除双边手续费。"""
import pandas as pd

from app.backtest.metrics import computeMetrics, extractTrades
from app.backtest.strategies.base import Strategy
from app.core.config import DEFAULT_FEE_RATE


def runBacktest(
    bars: pd.DataFrame, strategy: Strategy, feeRate: float = DEFAULT_FEE_RATE
) -> dict:
    """对单标的日线执行回测。

    Args:
        bars: 标准 OHLCV 数据(含 date 列,升序)。
        strategy: 策略实例,产出 0/1 目标持仓。
        feeRate: 单边手续费率,仓位变动时按变动量计双边。

    Returns:
        {equityCurve, metrics, trades, positions}
    """
    if bars.empty:
        raise ValueError("行情数据为空,无法回测")

    df = bars.sort_values("date").reset_index(drop=True)
    signals = strategy.generateSignals(df).reindex(df["date"].values).fillna(0).astype(int)

    close = df["close"].reset_index(drop=True)
    close.index = pd.DatetimeIndex(df["date"])

    # T 日信号 T+1 生效,避免前视偏差
    positions = signals.shift(1).fillna(0).astype(int)

    # 日收益 = 持仓 * 收盘涨跌幅 - 手续费(仓位变动日扣双边)
    dailyReturn = close.pct_change().fillna(0)
    turnover = positions.diff().abs().fillna(positions.abs())
    strategyReturn = positions * dailyReturn - turnover * feeRate * 2

    equity = (1 + strategyReturn).cumprod()
    # 首日净值从 1 开始
    equity.iloc[0] = 1.0 * (1 + strategyReturn.iloc[0])

    equityCurve = [
        {"date": str(d.date()), "equity": round(float(v), 4)}
        for d, v in equity.items()
    ]
    metrics = computeMetrics(equity, positions)
    trades = extractTrades(positions, equity)

    return {
        "equityCurve": equityCurve,
        "metrics": metrics,
        "trades": trades,
        "positions": [
            {"date": str(d.date()), "position": int(p)} for d, p in positions.items()
        ],
    }
