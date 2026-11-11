"""全局配置:数据目录、服务端口等。"""
from pathlib import Path

# 项目根目录(quant/)
BASE_DIR = Path(__file__).resolve().parents[3]

# 行情数据 Parquet 存储目录
DATA_DIR = BASE_DIR / "data"

# 默认单边手续费(万三)
DEFAULT_FEE_RATE = 0.0003

# 无风险利率(用于夏普比率)
RISK_FREE_RATE = 0.02

# 每年交易日数量(年化用)
TRADING_DAYS_PER_YEAR = 252

# 允许的市场枚举
SUPPORTED_MARKETS = ("cn", "hk", "us")
