@echo off
chcp 65001 >nul
powershell.exe -NoProfile -File "%~dp0proof\windows\stop-owned.ps1" -PackageRoot "%~dp0"
pause
