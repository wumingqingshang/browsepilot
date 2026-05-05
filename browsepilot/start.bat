@echo off
chcp 65001 >nul
:: BrowsePilot — 一键启动所有服务

setlocal
cd /d "%~dp0"

echo ==========================================
echo   BrowsePilot
echo ==========================================
echo.

:: ---- Check venv ----
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found, run: uv sync
    pause
    exit /b 1
)

:: ---- MCP Server (Port 8090) ----
echo [1/3] Starting MCP Server...
start "BrowsePilot-MCP" cmd /k ".venv\Scripts\python.exe -m browser_mcp.main"
echo   MCP Server started

timeout /t 2 /nobreak >nul

:: ---- Backend (Port 8000) ----
echo [2/3] Starting Backend...
start "BrowsePilot-Backend" cmd /k ".venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000"
echo   Backend started

timeout /t 2 /nobreak >nul

:: ---- Frontend (Port 8501) ----
echo [3/3] Starting Frontend...
start "BrowsePilot-Frontend" cmd /k ".venv\Scripts\python.exe -m streamlit run frontend/streamlit_app.py --server.port 8501 --server.headless true"
echo   Frontend started

echo.
echo ==========================================
echo   MCP:      http://localhost:8090/sse
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:8501
echo ==========================================
echo.
echo Close each window to stop the service.
pause

endlocal
