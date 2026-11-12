"""受约束的策略解释器：无eval/exec，因子按实际可知时间向后匹配。"""
import numpy as np
import pandas as pd

from app.backtest.strategies.base import Strategy
from app.monitor.session import CLOSES, ZONES
from app.strategies.models import Operand, RuleGroup, StrategySpec
from app.strategies.store import loadFactor


def alignFactor(rows: pd.DataFrame, dates: pd.Series, market: str, maxAgeDays: int) -> pd.Series:
    cutoffs = pd.to_datetime([pd.Timestamp(d).date().isoformat() + "T" + CLOSES[market].isoformat() for d in dates])
    # 使用交易所本地日期的收盘时间，纽约夏令时由IANA时区处理。
    cutoffs = cutoffs.tz_localize(ZONES[market]).tz_convert("UTC")
    frame = rows.copy()
    frame["availableAt"] = pd.to_datetime(frame.availableAt, utc=True)
    aligned = pd.merge_asof(pd.DataFrame({"cutoff": cutoffs}), frame.sort_values("availableAt"),
                            left_on="cutoff", right_on="availableAt", direction="backward",
                            tolerance=pd.Timedelta(days=maxAgeDays))
    return pd.Series(aligned.value.to_numpy(), index=dates.index, dtype=float)


class RuleStrategy(Strategy):
    name = "editable_rules"

    def __init__(self, spec: StrategySpec, market: str, symbol: str):
        self.spec, self.market, self.symbol = spec, market, symbol
        self.factorSources = {}

    def generateSignals(self, bars: pd.DataFrame) -> pd.Series:
        frame = bars.reset_index(drop=True)
        cache = {}
        factorFrames = {}
        def operand(item: Operand):
            key = item.model_dump_json()
            if key in cache:
                return cache[key]
            close = frame.close
            n = item.window
            if item.kind == "constant": value = pd.Series(item.value, index=frame.index)
            elif item.kind in ("close", "open", "high", "low", "volume"): value = frame[item.kind]
            elif item.kind == "sma": value = close.rolling(n, min_periods=n).mean()
            elif item.kind == "return": value = close.pct_change(n, fill_method=None)
            elif item.kind == "volatility": value = close.pct_change(fill_method=None).rolling(n, min_periods=n).std() * np.sqrt(252)
            elif item.kind == "drawdown": value = close / close.rolling(n, min_periods=n).max() - 1
            elif item.kind == "volume_ratio": value = frame.volume / frame.volume.shift(1).rolling(n, min_periods=n).mean().replace(0, np.nan)
            elif item.kind == "rsi":
                delta = close.diff()
                gain = delta.clip(lower=0).rolling(n, min_periods=n).mean()
                loss = (-delta.clip(upper=0)).rolling(n, min_periods=n).mean()
                value = (100 - 100 / (1 + gain / loss.replace(0, np.nan))).where(loss != 0, 100).where((gain != 0) | (loss != 0), 50)
            else:
                if item.factor not in factorFrames:
                    factorFrames[item.factor] = loadFactor(self.market, self.symbol, item.factor)
                    self.factorSources[item.factor] = {"source": factorFrames[item.factor].attrs.get("source", "用户导入"), "observations": len(factorFrames[item.factor])}
                value = alignFactor(factorFrames[item.factor], frame.date, self.market, item.maxAgeDays)
            cache[key] = value.replace([np.inf, -np.inf], np.nan)
            return cache[key]
        def group(rule: RuleGroup):
            conditions = []
            for condition in rule.conditions:
                a, b = operand(condition.left), operand(condition.right)
                valid = a.notna() & b.notna()
                if condition.op in ("cross_above", "cross_below"):
                    valid &= a.shift(1).notna() & b.shift(1).notna()
                match condition.op:
                    case "gt": value = a > b
                    case "gte": value = a >= b
                    case "lt": value = a < b
                    case "lte": value = a <= b
                    case "cross_above": value = (a > b) & (a.shift(1) <= b.shift(1))
                    case "cross_below": value = (a < b) & (a.shift(1) >= b.shift(1))
                conditions.append(value & valid)
            matrix = pd.concat(conditions, axis=1)
            return matrix.all(axis=1) if rule.logic == "all" else matrix.any(axis=1)
        buy, sell = group(self.spec.entry), group(self.spec.exit)
        holding = pending = False
        entryPrice, held = 0.0, 0
        signals = []
        for i, row in enumerate(frame.itertuples()):
            if pending:
                entryPrice, held, pending = float(row.open), 0, False
            if holding:
                held += 1
                ret = float(row.close) / entryPrice - 1
                risk = ((self.spec.stopLossPct is not None and ret <= -self.spec.stopLossPct)
                        or (self.spec.takeProfitPct is not None and ret >= self.spec.takeProfitPct)
                        or (self.spec.maxHoldingBars is not None and held >= self.spec.maxHoldingBars))
                if sell.iloc[i] or risk:
                    holding = False
            elif buy.iloc[i] and not sell.iloc[i]:
                holding, pending = True, True
            signals.append(int(holding))
        return pd.Series(signals, index=pd.DatetimeIndex(frame.date), dtype=int)


class FixedSignals(Strategy):
    """一次执行共用一份数据快照，回测和最新信号不得重复读取变化中的因子。"""
    def __init__(self, signals: pd.Series):
        self.signals = signals

    def generateSignals(self, bars: pd.DataFrame) -> pd.Series:
        return self.signals.reindex(pd.DatetimeIndex(bars.date))
