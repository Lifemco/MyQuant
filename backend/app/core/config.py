"""全局配置:数据目录、服务端口等。"""
from pathlib import Path
import os

# 项目根目录(quant/)
BASE_DIR = Path(__file__).resolve().parents[3]

# 行情数据 Parquet 存储目录
DATA_DIR = Path(os.environ.get("QUANT_DATA_DIR", str(BASE_DIR / "data"))).expanduser().resolve()
CORS_ORIGINS = [value.strip() for value in os.environ.get(
    "QUANT_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",") if value.strip()]

# 默认单边手续费(万三)
DEFAULT_FEE_RATE = 0.0003

# 无风险利率(用于夏普比率)
RISK_FREE_RATE = 0.02

# 每年交易日数量(年化用)
TRADING_DAYS_PER_YEAR = 252

# 允许的市场枚举
SUPPORTED_MARKETS = ("cn", "hk", "us")
