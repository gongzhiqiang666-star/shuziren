@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0proof\windows\preflight.ps1" -PackageRoot "%~dp0"
echo.
if errorlevel 1 (echo 环境检查未通过，请查看 reports\preflight。) else (echo 环境检查通过。)
pause
