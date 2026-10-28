@echo off
chcp 65001 > nul
echo ========================================================
echo   투자거울 (Investment Mirror) AI 복기 비서 로컬 실행기
echo ========================================================
echo.
echo [1] 웹 서비스 및 API 서버 시작: http://127.0.0.1:8000
echo [2] Swagger API 문서: http://127.0.0.1:8000/docs
echo.
echo 브라우저를 자동으로 엽니다...
start http://127.0.0.1:8000
python main.py
pause
