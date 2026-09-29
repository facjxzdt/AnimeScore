@echo off
chcp 65001 >nul
echo ==========================================
echo AnimeScore API Server
echo ==========================================
echo.

REM 激活虚拟环境
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
) else (
    call venv\Scripts\activate.bat
)

REM 设置 Python 环境变量
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo Virtual environment activated.
echo.
echo API Endpoints:
echo   - Swagger UI: http://localhost:5001/docs
echo   - Health Check: http://localhost:5001/api/v1/health/
echo   - Catalog: http://localhost:5001/api/v1/catalog/
echo   - New API: http://localhost:5001/api/v1/anime/airing
echo.
echo Press Ctrl+C to stop the server.
echo.

REM 启动 API 服务
python -m uvicorn web_api.main:app --host 0.0.0.0 --port 5001 --reload

pause
