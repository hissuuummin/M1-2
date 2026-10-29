@echo off
chcp 65001 > nul
cd /d "%~dp0"
set LOG=%~dp0push_log.log
echo [%date% %time%] start > "%LOG%"

echo [1/5] Check files to commit...
git status --short >> "%LOG%" 2>&1

echo [2/5] Commit changes...
git add -A >> "%LOG%" 2>&1
git reset -q -- commit_msg.txt >> "%LOG%" 2>&1
git commit -q -F commit_msg.txt >> "%LOG%" 2>&1
echo commit exit %errorlevel% >> "%LOG%"
del commit_msg.txt

echo [3/5] Connect GitHub repository...
git remote get-url origin > nul 2>&1
if errorlevel 1 (
  git remote add origin https://github.com/hissuuummin/M1-2.git >> "%LOG%" 2>&1
) else (
  git remote set-url origin https://github.com/hissuuummin/M1-2.git >> "%LOG%" 2>&1
)
git branch -M main >> "%LOG%" 2>&1

echo [4/5] Merge the README commit already on GitHub (a login window may open)...
git pull origin main --allow-unrelated-histories --no-rebase -X ours --no-edit >> "%LOG%" 2>&1
echo pull exit %errorlevel% >> "%LOG%"

echo [5/5] Upload...
git push -u origin main >> "%LOG%" 2>&1
echo push exit %errorlevel% >> "%LOG%"

echo [%date% %time%] done >> "%LOG%"
echo.
echo Done. Go back to Claude and say "done".
pause
