#!/bin/bash
echo "============================================"
echo "  BrowsePilot - Starting All Services"
echo "============================================"
echo ""

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "[1/3] Starting browser-mcp on port 8090..."
cd "$ROOT" && ../.venv/bin/python -m browser_mcp.server &
sleep 3

echo "[2/3] Starting FastAPI backend on port 8000..."
cd "$ROOT/backend" && ../../.venv/bin/python -m uvicorn app.main:app --port 8000 &
sleep 3

echo "[3/3] Starting Streamlit frontend on port 8501..."
cd "$ROOT" && ../.venv/bin/python -m streamlit run frontend/streamlit_app.py &

echo ""
echo "============================================"
echo "  All services started!"
echo "  Frontend: http://localhost:8501"
echo "  Backend:  http://localhost:8000"
echo "  MCP:      http://localhost:8090"
echo "============================================"
