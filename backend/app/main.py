import os
import sys

# Ensure backend and root are in sys.path so app can be run from anywhere
_current_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(_current_dir)
_root_dir = os.path.dirname(_backend_dir)
for _p in [_backend_dir, _current_dir, _root_dir]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

try:
    from app.api.routers import chat, conversations, data, health, review, stocks, trades
    from app.core.config import settings
    from app.core.firebase import get_firestore_client, is_mock_firestore
except ImportError:
    from backend.app.api.routers import chat, conversations, data, health, review, stocks, trades
    from backend.app.core.config import settings
    from backend.app.core.firebase import get_firestore_client, is_mock_firestore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("investment_mirror.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize Firestore & check readiness
    logger.info("Starting 투자거울 (Investment Mirror) API Service...")
    if settings.dev_mode_effective:
        logger.warning("DEV_MODE is ON: all API endpoints are accessible without login. Use only on your own computer.")
    db = get_firestore_client()
    if is_mock_firestore():
        logger.info("Running in Mock Firestore mode for local development/testing.")
    else:
        logger.info("Running with connected Firebase Firestore.")
    yield
    # Shutdown
    logger.info("Shutting down 투자거울 API Service.")


app = FastAPI(
    title="투자거울 (Investment Mirror) API",
    description="내 매매를 시장(코스피)과 종목의 흐름에 비춰 보며 복기를 돕는 AI 비서 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# CORS Middleware
origins = settings.cors_origins
logger.info(f"CORS allowed origins: {origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True if origins != ["*"] else False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers under /api
app.include_router(health.router, prefix="/api")
app.include_router(data.router, prefix="/api")
app.include_router(conversations.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(review.router, prefix="/api")
app.include_router(stocks.router, prefix="/api")
app.include_router(trades.router, prefix="/api")

# Static files and Frontend Single Page App serving (로컬 실행 편의용. 운영 프론트는 Vercel)
_frontend_dir = os.path.realpath(os.path.join(_root_dir, "frontend"))


def _safe_frontend_path(filename: str):
    """frontend 폴더 안의 파일만 돌려줍니다. '..' 등으로 폴더 밖을 가리키면 None."""
    target = os.path.realpath(os.path.join(_frontend_dir, filename))
    try:
        inside = os.path.commonpath([_frontend_dir, target]) == _frontend_dir
    except ValueError:  # Windows에서 드라이브가 다른 경우
        inside = False
    if not inside:
        return None
    # 숨김 파일(.env 등)은 frontend 안에 있어도 내려주지 않습니다.
    rel_parts = os.path.relpath(target, _frontend_dir).split(os.sep)
    if any(part.startswith(".") for part in rel_parts):
        return None
    return target


if os.path.isdir(_frontend_dir):
    @app.get("/", include_in_schema=False)
    def serve_frontend_root():
        return FileResponse(os.path.join(_frontend_dir, "index.html"))

    @app.get("/{filename:path}", include_in_schema=False)
    def serve_frontend_files(filename: str):
        # 없는 API 경로는 index.html이 아니라 404 JSON으로 응답
        if filename == "api" or filename.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})

        target = _safe_frontend_path(filename)
        if target is None:
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        if os.path.isfile(target):
            return FileResponse(target)
        return FileResponse(os.path.join(_frontend_dir, "index.html"))
else:
    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/docs")


# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled Exception on %s", request.url.path, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
