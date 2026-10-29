@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set LOG=%~dp0setup_log.log

echo ==================================================
echo  Investment Mirror - local setup and test
echo  (result is saved to setup_log.log)
echo ==================================================

echo [%date% %time%] start > "%LOG%"

where py > nul 2> nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)

if not exist venv\Scripts\python.exe (
  echo [1/4] Creating virtual environment...
  echo [1/4] create venv >> "%LOG%"
  %PY% -m venv venv >> "%LOG%" 2>&1
)
if not exist venv\Scripts\python.exe (
  echo FAILED: could not create venv. Is Python installed?
  echo FAILED venv >> "%LOG%"
  pause
  exit /b 1
)

echo [2/4] Installing packages (takes a few minutes the first time)...
echo [2/4] pip install >> "%LOG%"
venv\Scripts\python.exe -m pip install --upgrade pip >> "%LOG%" 2>&1
venv\Scripts\python.exe -m pip install -r backend\requirements.txt >> "%LOG%" 2>&1
if errorlevel 1 (
  echo FAILED: package install. See setup_log.log
  echo FAILED pip >> "%LOG%"
  pause
  exit /b 1
)

echo [3/4] Loading real KOSPI closes (last 365 days)...
echo [3/4] load_kospi >> "%LOG%"
venv\Scripts\python.exe backend\scripts\load_kospi.py >> "%LOG%" 2>&1
echo load_kospi exit code %errorlevel% >> "%LOG%"

echo [4/4] Running tests...
echo [4/4] pytest >> "%LOG%"
pushd backend
..\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider >> "%LOG%" 2>&1
echo pytest exit code %errorlevel% >> "%LOG%"
popd

echo [%date% %time%] done >> "%LOG%"
echo.
echo Done. Go back to Claude and say "done".
pause
