from datetime import datetime, timezone
from fastapi import APIRouter
from app.core.config import settings
from app.core.firebase import is_mock_firestore

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    """
    서버 상태 확인 및 Render 무료 티어 콜드스타트 해소용 엔드포인트 (인증 불필요)
    프론트는 auth_mode 값을 보고 로그인 화면을 띄울지 정합니다. 비밀값은 포함하지 않습니다.
    """
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "auth_mode": "dev" if settings.dev_mode_effective else "firebase",
        "storage": "local" if is_mock_firestore() else "firestore",
        "ai_enabled": settings.openai_enabled,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
