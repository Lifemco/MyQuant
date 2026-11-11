#!/usr/bin/env bash
# 启动本地工作台。优先显式 PYTHON_BIN、.venv、conda quant，最后使用 python3。
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -z "${PYTHON_BIN:-}" ]; then
  if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
  elif command -v conda >/dev/null 2>&1 && [ -x "$(conda info --base)/envs/quant/bin/python" ]; then
    PYTHON_BIN="$(conda info --base)/envs/quant/bin/python"
  else
    PYTHON_BIN="$(command -v python3 || true)"
  fi
fi
if [ ! -x "$PYTHON_BIN" ] || ! "$PYTHON_BIN" -c 'import fastapi, uvicorn, pandas, pyarrow, httpx' 2>/dev/null; then
  echo "请先创建Python环境并安装依赖："
  echo "python3 -m venv .venv"
  echo ".venv/bin/python -m pip install -r backend/requirements-lock.txt"
  exit 1
fi
if [ ! -x "$ROOT_DIR/frontend/node_modules/.bin/vite" ]; then
  echo "请先执行：cd frontend && npm ci"
  exit 1
fi
portInUse() {
  "$PYTHON_BIN" - "$1" <<'PY'
import socket, sys
with socket.socket() as s:
    s.settimeout(.3)
    sys.exit(0 if s.connect_ex(('127.0.0.1', int(sys.argv[1]))) == 0 else 1)
PY
}
PIDS=()
cleanup() {
  if [ ${#PIDS[@]} -gt 0 ]; then
    kill "${PIDS[@]}" 2>/dev/null || true
    for pid in "${PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if ! portInUse 8080; then
  (cd "$ROOT_DIR/backend" && exec "$PYTHON_BIN" -m uvicorn app.main:app --host 127.0.0.1 --port 8080) &
  PIDS+=($!)
else
  echo "8080 已监听，复用现有后端"
fi
if ! portInUse 5173; then
  (cd "$ROOT_DIR/frontend" && exec node_modules/.bin/vite --host 127.0.0.1 --port 5173 --strictPort) &
  PIDS+=($!)
else
  echo "5173 已监听，复用现有前端"
fi
echo "打开 http://localhost:5173 ，Ctrl+C 停止本次启动的服务。"
if [ ${#PIDS[@]} -eq 0 ]; then exit 0; fi
# 兼容macOS自带Bash 3.2；任一子进程退出便停止另一服务。
while true; do
  for pid in "${PIDS[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      wait "$pid"
      exit 0
    fi
  done
  sleep 1
done
