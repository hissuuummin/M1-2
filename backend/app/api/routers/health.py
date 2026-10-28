from datetime import datetime, timezone
from fastapi import APIRouter
from app.core.config import settings
from app.core.firebase import is_mock_firestore

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    """
    서버 상태 확인 및 Render 무료 티어 콜드스타트 해소용 엔드포인트 (인증 불필요)
    """
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "is_mock_firestore": is_mock_firestore(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
