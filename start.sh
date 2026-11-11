#!/usr/bin/env bash
# 量化工作台一键启动:后端 FastAPI(8080) + 前端 Vite(5173)
# 用法: ./start.sh    Ctrl+C 同时停止两个服务
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------- 后端解释器:conda quant 环境 ----------
CONDA_ENV="quant"
CONDA_BASE="$(conda info --base 2>/dev/null || true)"
# conda 不在 PATH 时,遍历常见安装目录兜底
if [ -z "$CONDA_BASE" ]; then
  for candidate in /opt/anaconda3 "$HOME/anaconda3" /opt/miniconda3 "$HOME/miniconda3"; do
    if [ -x "$candidate/envs/$CONDA_ENV/bin/python" ]; then
      CONDA_BASE="$candidate"
      break
    fi
  done
fi
PYTHON_BIN="$CONDA_BASE/envs/$CONDA_ENV/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "[错误] 未找到 conda $CONDA_ENV 环境的 python: $PYTHON_BIN"
  echo "请先执行: conda create -n $CONDA_ENV python=3.13 -y"
  echo "          $CONDA_BASE/envs/$CONDA_ENV/bin/pip install -r backend/requirements.txt"
  exit 1
fi

# 端口占用检测:已监听则返回 0
portInUse() {
  lsof -i ":$1" -sTCP:LISTEN >/dev/null 2>&1
}

echo "====== 量化工作台启动 ======"

# ---------- 依赖检查 ----------
if ! "$PYTHON_BIN" -c "import fastapi, uvicorn" 2>/dev/null; then
  echo "[提示] 后端依赖缺失,请先执行: $PYTHON_BIN -m pip install -r backend/requirements.txt"
  exit 1
fi
if [ ! -d "$ROOT_DIR/frontend/node_modules" ]; then
  echo "[提示] 前端依赖缺失,请先执行: cd frontend && npm install"
  exit 1
fi

PIDS=()

# ---------- 启动后端 ----------
if portInUse 8080; then
  echo "[后端] 8080 端口已在运行,复用现有进程"
else
  echo "[后端] 启动 FastAPI(conda:$CONDA_ENV)→ http://localhost:8080"
  # exec 让子进程直接替换子 shell,$! 即为真实进程 PID
  (cd "$ROOT_DIR/backend" && exec "$PYTHON_BIN" -m uvicorn app.main:app --port 8080) &
  PIDS+=($!)
fi

# ---------- 启动前端 ----------
if portInUse 5173; then
  echo "[前端] 5173 端口已在运行,复用现有进程"
else
  echo "[前端] 启动 Vite → http://localhost:5173"
  # 直接调 vite 而非 npm run dev,避免 npm 包装层导致 kill 失效
  (cd "$ROOT_DIR/frontend" && exec node_modules/.bin/vite) &
  PIDS+=($!)
fi

# ---------- 退出清理 ----------
cleanup() {
  echo ""
  echo "正在停止服务..."
  # 空数组在 bash 3.2 + set -u 下展开会报错,先判空
  if [ ${#PIDS[@]} -gt 0 ]; then
    kill "${PIDS[@]}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "=============================="
echo "  打开浏览器: http://localhost:5173"
echo "  API 文档:   http://localhost:8080/docs"
echo "=============================="

# 等待子进程;任一退出则结束脚本
if [ ${#PIDS[@]} -gt 0 ]; then
  wait "${PIDS[@]}"
else
  echo "两个服务均已在运行,本脚本无需驻留。"
fi
