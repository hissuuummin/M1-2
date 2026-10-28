import logging
from typing import Optional
from fastapi import Header, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth
from app.core.config import settings

logger = logging.getLogger("investment_mirror.auth")
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials_auth: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> dict:
    """
    Validates Firebase ID token and verifies ALLOWED_EMAIL.
    In DEV_MODE, allows local dev token or unauthenticated local dev testing.
    """
    token = credentials_auth.credentials if credentials_auth else None

    # Handle DEV_MODE or test tokens
    if settings.DEV_MODE:
        if not token or token == "dev-token" or token == "test-token":
            return {
                "uid": "dev_user_001",
                "email": settings.ALLOWED_EMAIL or "tester@investment-mirror.local",
                "name": "테스터",
                "is_dev": True
            }

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 토큰이 제공되지 않았습니다. (Authorization header missing)"
        )

    try:
        # Verify Firebase ID token
        decoded_token = auth.verify_id_token(token)
        user_email = decoded_token.get("email", "")

        # Check ALLOWED_EMAIL restriction if configured
        if settings.ALLOWED_EMAIL and settings.ALLOWED_EMAIL.strip():
            allowed_list = [e.strip().lower() for e in settings.ALLOWED_EMAIL.split(",") if e.strip()]
            if user_email.lower() not in allowed_list:
                logger.warning(f"Unauthorized email attempted access: {user_email}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"접근이 허용되지 않은 계정입니다. ({user_email})"
                )

        return decoded_token
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"유효하지 않거나 만료된 인증 토큰입니다: {str(e)}"
        )
