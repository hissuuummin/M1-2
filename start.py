"""
투자거울 (Investment Mirror) - One-Click Launcher
브라우저를 자동으로 열고 백엔드 API 및 통합 웹 서비스를 함께 구동합니다.
"""
import os
import sys
import threading
import time
import webbrowser

root_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(root_dir, "backend")
for p in [backend_dir, root_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)


def open_browser():
    time.sleep(1.5)
    print("🌐 브라우저를 열어 웹 서비스를 표시합니다: http://127.0.0.1:8000")
    webbrowser.open("http://127.0.0.1:8000")


if __name__ == "__main__":
    print("========================================================")
    print("   투자거울 (Investment Mirror) 로컬 서비스 구동 중")
    print("========================================================")
    print("👉 웹 서비스 접속: http://127.0.0.1:8000")
    print("👉 Swagger API 문서: http://127.0.0.1:8000/docs")
    print("👉 종료하려면 Ctrl + C 를 누르세요.")

    # Open browser automatically in background thread
    threading.Thread(target=open_browser, daemon=True).start()

    from backend.app.main import app
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
