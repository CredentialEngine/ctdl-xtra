@echo off
setlocal EnableExtensions
set "HERE=%~dp0.."
set "SCRIPT=%HERE%\xtra_cli.py"
where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python "%SCRIPT%" %*
  exit /b %ERRORLEVEL%
)
py -3 "%SCRIPT%" %*
exit /b %ERRORLEVEL%
