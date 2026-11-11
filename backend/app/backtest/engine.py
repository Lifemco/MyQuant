"""T日收盘信号，下一根交易日开盘执行；单边手续费、现金/股数记账。"""
import math

import pandas as pd

from app.backtest.metrics import computeMetrics
from app.backtest.strategies.base import Strategy
from app.core.config import DEFAULT_FEE_RATE


def runBacktest(bars: pd.DataFrame, strategy: Strategy, feeRate: float = DEFAULT_FEE_RATE) -> dict:
    if bars.empty:
        raise ValueError("行情数据为空,无法回测")
    if not math.isfinite(feeRate) or not 0 <= feeRate <= 0.01:
        raise ValueError("单边手续费率必须在0~0.01之间")
    df = bars.sort_values("date").reset_index(drop=True)
    if df["date"].duplicated().any() or df[["open", "close"]].isna().any().any():
        raise ValueError("行情包含重复日期或缺失价格")
    if not df[["open", "close"]].map(lambda x: math.isfinite(x) and x > 0).all().all():
        raise ValueError("成交与收盘价格必须为正的有限数值")
    signals = strategy.generateSignals(df).reindex(df["date"].values)
    if signals.isna().any() or not signals.isin([0, 1]).all():
        raise ValueError("策略必须返回与行情日期对齐的0/1持仓")
    positions = signals.shift(1).fillna(0).astype(int)
    cash, shares = 1.0, 0.0
    values, trades = [], []
    entry = None
    for row, target in zip(df.itertuples(), positions):
        if target == 1 and shares == 0:
            entry = {"entryDate": str(row.date.date()), "entryPrice": float(row.open), "cost": cash}
            # 买入金额 + 佣金不得超过现金，不使用杠杆或负现金。
            shares = cash / (float(row.open) * (1 + feeRate))
            cash = 0.0
        elif target == 0 and shares > 0:
            cash = shares * float(row.open) * (1 - feeRate)
            trades.append({"entryDate": entry["entryDate"], "exitDate": str(row.date.date()),
                           "entryPrice": entry["entryPrice"], "exitPrice": float(row.open),
                           "pnlPct": cash / entry["cost"] - 1})
            shares, entry = 0.0, None
        values.append(cash + shares * float(row.close))
    if entry is not None:
        trades.append({"entryDate": entry["entryDate"], "exitDate": None,
                       "entryPrice": entry["entryPrice"], "exitPrice": None,
                       "pnlPct": values[-1] / entry["cost"] - 1})
    equity = pd.Series(values, index=pd.DatetimeIndex(df["date"]))
    return {
        "equityCurve": [{"date": str(d.date()), "equity": round(float(v), 8)} for d, v in equity.items()],
        "metrics": computeMetrics(equity, positions, trades),
        "trades": [{**t, "pnlPct": round(t["pnlPct"], 8)} for t in trades],
        "positions": [{"date": str(pd.Timestamp(d).date()), "position": int(p)} for d, p in positions.items()],
    }
