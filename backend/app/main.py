"""FastAPI 入口:注册路由、CORS 与全局异常处理。"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.core.config import CORS_ORIGINS, DATA_DIR
import tempfile

from app.api import backtest, data, market, monitor, strategies, watchlist

app = FastAPI(title="Quant Workbench", version="0.1.0")

# 本地开发放开跨域(Vite 默认 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data.router)
app.include_router(backtest.router)
app.include_router(watchlist.router)
app.include_router(monitor.router)
app.include_router(market.router)
app.include_router(strategies.router)


@app.exception_handler(ValueError)
async def invalidInputHandler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def invalidRequestHandler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # 不回显可能含私密数据或NaN的原始请求字段。
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": error["loc"], "msg": error["msg"], "type": error["type"]} for error in exc.errors()
    ]})


@app.exception_handler(KeyError)
async def unknownStrategyHandler(request: Request, exc: KeyError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def globalExceptionHandler(request: Request, exc: Exception) -> JSONResponse:
    """统一错误格式:{"detail": "..."}"""
    return JSONResponse(status_code=500, content={"detail": f"服务器内部错误: {exc}"})


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/health/live")
def liveness() -> dict:
    return {"status": "ok"}


@app.get("/api/health/ready")
def readiness():
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=DATA_DIR):
            pass
    except OSError:
        return JSONResponse(status_code=503, content={"status": "not_ready", "detail": "数据卷不可写"})
    return {"status": "ready"}
