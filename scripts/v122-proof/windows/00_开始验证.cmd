@echo off
setlocal
chcp 65001 >nul
set "ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%proof\windows\start-server.ps1" -PackageRoot "%ROOT%"
if errorlevel 1 pause & exit /b 1
start "" "http://127.0.0.1:5157/"
echo.
echo 验证网页已打开。关闭此窗口不会删除素材。
echo 如需停止工具，请双击 99_停止验证.cmd。
pause
