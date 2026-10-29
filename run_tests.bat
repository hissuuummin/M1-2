@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0backend"
echo Running tests... (result is saved to setup_log.log)
..\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider > "%~dp0setup_log.log" 2>&1
echo pytest exit code %errorlevel% >> "%~dp0setup_log.log"
type "%~dp0setup_log.log" | findstr /C:"passed" /C:"failed"
echo.
echo Done. Go back to Claude and say "done".
pause
