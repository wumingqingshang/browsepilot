@echo off
echo ============================================
echo   BrowsePilot - Starting All Services
echo ============================================
echo.

set ROOT=%~dp0

echo [1/3] Starting browser-mcp on port 8090...
start "browser-mcp" cmd /c "cd /d %ROOT% && ..\.venv\Scripts\python.exe -m browser_mcp.server"
timeout /t 3 >nul

echo [2/3] Starting FastAPI backend on port 8000...
start "backend" cmd /c "cd /d %ROOT%backend && ..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"
timeout /t 3 >nul

echo [3/3] Starting Streamlit frontend on port 8501...
start "frontend" cmd /c "cd /d %ROOT% && ..\.venv\Scripts\python.exe -m streamlit run frontend/streamlit_app.py"

echo.
echo ============================================
echo   All services started!
echo   Frontend: http://localhost:8501
echo   Backend:  http://localhost:8000
echo   MCP:      http://localhost:8090
echo ============================================
pause
