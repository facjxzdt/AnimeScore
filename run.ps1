#!/usr/bin/env pwsh
# AnimeScore API Server Launcher

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "AnimeScore API Server" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# 激活虚拟环境
$venvPath = ".\venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    & $venvPath
    Write-Host "Virtual environment activated." -ForegroundColor Green
} else {
    Write-Host "Error: Virtual environment not found!" -ForegroundColor Red
    exit 1
}

# 设置环境变量
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Write-Host ""
Write-Host "API Endpoints:" -ForegroundColor Yellow
Write-Host "  - Swagger UI: http://localhost:5001/docs"
Write-Host "  - Health Check: http://localhost:5001/api/v1/health/"
Write-Host "  - Old API: http://localhost:5001/air"
Write-Host "  - New API: http://localhost:5001/api/v1/anime/airing"
Write-Host ""
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor Magenta
Write-Host ""

# 启动 API 服务
python -m uvicorn web_api.main:app --host 0.0.0.0 --port 5001 --reload
