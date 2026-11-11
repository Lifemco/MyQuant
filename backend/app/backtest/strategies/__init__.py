"""策略注册表:按名称查找策略类。"""
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
    return _REGISTRY[name](**params)


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
