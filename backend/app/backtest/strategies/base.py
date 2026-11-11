"""策略基类:策略只负责产出目标持仓信号(0/1),执行与计费由引擎负责。"""
from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    """向量化策略接口,仅做多/空仓两态。"""

    #: 策略唯一标识,用于 API 路由
    name: str = ""
    #: 展示名称
    label: str = ""
    #: 策略说明(来源/口径)
    desc: str = ""
    #: 参数说明 {参数名: {type, default, min, max, desc}}
    paramsSchema: dict = {}

    def __init__(self, **params) -> None:
        self.params = params

    @abstractmethod
    def generateSignals(self, bars: pd.DataFrame) -> pd.Series:
        """根据行情生成目标持仓序列(1=持有,0=空仓),index 与 bars 的 date 对齐。"""
        raise NotImplementedError
