@echo off
setlocal

pushd "%~dp0" || exit /b 1
start "" powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0tools\agent_run.ps1" tools.gui
set "launcher_exit=%errorlevel%"
popd

exit /b %launcher_exit%
