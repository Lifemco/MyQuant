"""FastAPI 入口:注册路由、CORS 与全局异常处理。"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import backtest, data, monitor, watchlist

app = FastAPI(title="Quant Workbench", version="0.1.0")

# 本地开发放开跨域(Vite 默认 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data.router)
app.include_router(backtest.router)
app.include_router(watchlist.router)
app.include_router(monitor.router)


@app.exception_handler(ValueError)
async def invalidInputHandler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


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
