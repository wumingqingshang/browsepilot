#!/usr/bin/env bash
# BrowsePilot — 一键启动所有服务 (MCP + Backend + Frontend)
# Usage: bash start.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtualenv if present
if [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Clean up background processes on exit
cleanup() {
    echo ""
    echo "正在停止所有服务..."
    kill $MCP_PID $BACKEND_PID $FRONTEND_PID 2>/dev/null
    wait $MCP_PID $BACKEND_PID $FRONTEND_PID 2>/dev/null
    echo "所有服务已停止"
}
trap cleanup EXIT INT TERM

echo "=========================================="
echo "  BrowsePilot — 启动所有服务"
echo "=========================================="

# ---- MCP Server (Port 8090) ----
echo "[1/3] 启动 MCP Server (port 8090)..."
python -m browser_mcp.main &
MCP_PID=$!
sleep 2
echo "  MCP Server PID: $MCP_PID"

# ---- Backend (Port 8000) ----
echo "[2/3] 启动 Backend (port 8000)..."
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!
sleep 2
echo "  Backend PID: $BACKEND_PID"

# ---- Frontend (Port 8501) ----
echo "[3/3] 启动 Frontend (port 8501)..."
streamlit run frontend/streamlit_app.py --server.port 8501 --server.headless true &
FRONTEND_PID=$!
sleep 3
echo "  Frontend PID: $FRONTEND_PID"

echo ""
echo "=========================================="
echo "  所有服务已启动"
echo "  MCP:      http://localhost:8090/sse"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:8501"
echo "=========================================="
echo ""
echo "按 Ctrl+C 停止所有服务"

# Wait for all background processes
wait
