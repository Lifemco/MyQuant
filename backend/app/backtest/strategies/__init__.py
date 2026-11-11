"""策略注册表与服务端参数校验。"""
import math
from app.backtest.strategies.base import Strategy
from app.backtest.strategies.rsi_reversion import RsiReversionStrategy
from app.backtest.strategies.s1_trend_ma import S1TrendMaStrategy
from app.backtest.strategies.s2_volume_break import S2VolumeBreakStrategy
from app.backtest.strategies.sma_cross import SmaCrossStrategy

_REGISTRY: dict[str, type[Strategy]] = {
    SmaCrossStrategy.name: SmaCrossStrategy,
    RsiReversionStrategy.name: RsiReversionStrategy,
    S1TrendMaStrategy.name: S1TrendMaStrategy,
    S2VolumeBreakStrategy.name: S2VolumeBreakStrategy,
}


def getStrategy(name: str, **params) -> Strategy:
    """按名称实例化策略,未注册抛 KeyError。"""
    if name not in _REGISTRY:
        raise KeyError(f"未注册的策略: {name},可用: {list(_REGISTRY)}")
    cls = _REGISTRY[name]
    if params.keys() - cls.paramsSchema.keys():
        raise ValueError(f"未知策略参数: {sorted(params.keys() - cls.paramsSchema.keys())}")
    validated = {}
    for key, schema in cls.paramsSchema.items():
        value = params.get(key, schema["default"])
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{key} 必须是有限数值")
        if schema["type"] == "int" and int(value) != value:
            raise ValueError(f"{key} 必须是整数")
        if not schema["min"] <= value <= schema["max"]:
            raise ValueError(f"{key} 必须在 {schema['min']}~{schema['max']} 之间")
        validated[key] = int(value) if schema["type"] == "int" else float(value)
    if name == "sma_cross" and validated["fastWindow"] >= validated["slowWindow"]:
        raise ValueError("快线周期必须小于慢线周期")
    if name == "rsi_reversion" and validated["oversold"] >= validated["overbought"]:
        raise ValueError("超卖阈值必须小于超买阈值")
    return cls(**validated)


def listStrategies() -> list[dict]:
    """返回所有策略的元信息(含说明),供前端渲染参数表单。"""
    return [
        {
            "name": cls.name,
            "label": cls.label,
            "desc": getattr(cls, "desc", ""),
            "paramsSchema": cls.paramsSchema,
        }
        for cls in _REGISTRY.values()
    ]
