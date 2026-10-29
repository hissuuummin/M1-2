import logging
from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.core.config import settings

logger = logging.getLogger("investment_mirror.auth")
security = HTTPBearer(auto_error=False)

DEV_TOKENS = {"dev-token", "test-token"}


async def get_current_user(
    credentials_auth: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> dict:
    """
    Firebase ID 토큰을 검증하고 ALLOWED_EMAIL에 있는 계정만 통과시킵니다.
    DEV_MODE(로컬 전용)일 때만 토큰 없이 또는 dev-token으로 접근할 수 있습니다.
    """
    token = credentials_auth.credentials if credentials_auth else None

    if settings.dev_mode_effective and (not token or token in DEV_TOKENS):
        return {
            "uid": "dev_user_001",
            "email": settings.ALLOWED_EMAIL or "tester@investment-mirror.local",
            "name": "테스터",
            "is_dev": True
        }

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요해요."
        )

    try:
        # firebase_admin은 Firebase가 초기화된 경우에만 import (로컬 테스트 환경 보호)
        from firebase_admin import auth
        decoded_token = auth.verify_id_token(token)
    except Exception as e:
        # 토큰 내용이나 내부 오류 메시지는 응답에 넣지 않고 서버 로그에만 남깁니다.
        logger.warning("Token verification failed: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 만료되었거나 유효하지 않아요. 다시 로그인해 주세요."
        )

    allowed_list = [e.strip().lower() for e in settings.ALLOWED_EMAIL.split(",") if e.strip()]
    user_email = (decoded_token.get("email") or "").lower()

    # 운영 환경에서 ALLOWED_EMAIL을 비워 두면 아무 구글 계정이나 들어올 수 있으므로 막습니다.
    if not allowed_list and settings.is_production:
        logger.error("ALLOWED_EMAIL is empty in production. Rejecting all users.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="서버에 허용 계정(ALLOWED_EMAIL)이 설정되지 않았어요."
        )

    if allowed_list and user_email not in allowed_list:
        logger.warning("Unauthorized account attempted access.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="접근이 허용되지 않은 계정이에요."
        )

    return decoded_token
