@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo 请先运行 install.bat。
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.3.1
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install --index-url https://pypi.org/simple -r requirements-ai.txt
if errorlevel 1 goto failed
echo 本地图文、视频与语音依赖已安装。首次建立对应索引时会准备模型。
pause
exit /b 0
:failed
echo 安装未完成，请检查网络、代理设置和磁盘空间后重试。
pause
exit /b 1
