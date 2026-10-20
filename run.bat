@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo 请先运行 install.bat 安装基础依赖。
    pause
    exit /b 1
)
".venv\Scripts\python.exe" run.py %*
if errorlevel 1 pause
