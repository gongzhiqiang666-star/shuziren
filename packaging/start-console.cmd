@echo off
setlocal
if not defined SHUZIREN_PYTHON set "SHUZIREN_PYTHON=python"
pushd "%~dp0.." || exit /b 1
"%SHUZIREN_PYTHON%" -X utf8 -m scripts.local_console %*
set "code=%ERRORLEVEL%"
popd
exit /b %code%
