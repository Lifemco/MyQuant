"""绩效指标计算:收益率、夏普、最大回撤、胜率等。"""
import numpy as np
import pandas as pd

from app.core.config import RISK_FREE_RATE, TRADING_DAYS_PER_YEAR


def computeMetrics(equity: pd.Series, positions: pd.Series, trades: list[dict] | None = None) -> dict:
    """根据净值序列与持仓序列计算全部绩效指标。

    Args:
        equity: 净值序列(index 为日期,初始 1.0)。
        positions: 每日持仓(0/1),与 equity 对齐。

    Returns:
        包含各指标的字典,均保留 4 位小数。
    """
    returns = equity.pct_change().dropna()
    if returns.empty:
        return _emptyMetrics()

    totalReturn = equity.iloc[-1] / equity.iloc[0] - 1
    years = len(returns) / TRADING_DAYS_PER_YEAR
    annualReturn = (1 + totalReturn) ** (1 / years) - 1 if years > 0 else 0.0
    dailyVol = float(returns.std()) if len(returns) > 1 else 0.0
    annualVol = dailyVol * np.sqrt(TRADING_DAYS_PER_YEAR)
    sharpe = (
        (returns.mean() - RISK_FREE_RATE / TRADING_DAYS_PER_YEAR)
        / dailyVol * np.sqrt(TRADING_DAYS_PER_YEAR) if dailyVol > 0 else 0.0
    )

    drawdown = equity / equity.cummax() - 1
    maxDrawdown = drawdown.min()
    calmar = annualReturn / abs(maxDrawdown) if maxDrawdown < 0 else 0.0

    trades = extractTrades(positions, equity) if trades is None else trades
    closed = [t for t in trades if t["exitDate"] is not None]
    winRate = float(np.mean([t["pnlPct"] > 0 for t in closed])) if closed else 0.0

    return {
        "totalReturn": round(float(totalReturn), 4),
        "annualReturn": round(float(annualReturn), 4),
        "annualVolatility": round(float(annualVol), 4),
        "sharpeRatio": round(float(sharpe), 4),
        "maxDrawdown": round(float(maxDrawdown), 4),
        "calmarRatio": round(float(calmar), 4),
        "totalTrades": len(trades),
        "winRate": round(winRate, 4),
    }


def extractTrades(positions: pd.Series, equity: pd.Series) -> list[dict]:
    """从持仓序列还原成笔交易:0→1 开仓,1→0 平仓,按净值估算每笔盈亏百分比。"""
    trades: list[dict] = []
    entryDate, entryEquity = None, None
    prev = 0
    previousEquity = float(equity.iloc[0]) if len(equity) else 1.0
    for date, pos in positions.items():
        if prev == 0 and pos == 1:
            entryDate, entryEquity = date, previousEquity
        elif prev == 1 and pos == 0 and entryDate is not None:
            exitEquity = equity.loc[date]
            trades.append(
                {
                    "entryDate": str(entryDate.date() if hasattr(entryDate, "date") else entryDate),
                    "exitDate": str(date.date() if hasattr(date, "date") else date),
                    "pnlPct": round(float(exitEquity / entryEquity - 1), 4),
                }
            )
            entryDate, entryEquity = None, None
        prev = pos
        previousEquity = float(equity.loc[date])
    # 期末仍持仓记为未平仓单
    if entryDate is not None:
        lastDate = positions.index[-1]
        trades.append(
            {
                "entryDate": str(entryDate.date() if hasattr(entryDate, "date") else entryDate),
                "exitDate": None,
                "pnlPct": round(float(equity.iloc[-1] / entryEquity - 1), 4),
            }
        )
    return trades


def _emptyMetrics() -> dict:
    return {
        "totalReturn": 0.0, "annualReturn": 0.0, "annualVolatility": 0.0,
        "sharpeRatio": 0.0, "maxDrawdown": 0.0, "calmarRatio": 0.0,
        "totalTrades": 0, "winRate": 0.0,
    }
