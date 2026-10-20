@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.11 -m venv .venv
    if errorlevel 1 (
        echo 请先安装 Python 3.11（64 位），然后重试。
        pause
        exit /b 1
    )
)
".venv\Scripts\python.exe" -m pip install --index-url https://pypi.org/simple -r requirements.txt
if errorlevel 1 (
    echo 安装未完成，请检查网络或代理设置后重试。
    pause
    exit /b 1
)
echo 基础功能已安装。运行 run.bat 启动；图文、视频和台词索引请再运行 install-ai.bat。
pause
