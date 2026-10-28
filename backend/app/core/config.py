import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    PROJECT_NAME: str = "투자거울 (Investment Mirror)"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Firebase
    FIREBASE_SERVICE_ACCOUNT_JSON: Optional[str] = None
    FIREBASE_CREDENTIALS_PATH: Optional[str] = None

    # Auth & Security
    ALLOWED_EMAIL: str = ""
    DEV_MODE: bool = True  # Allows local development without live Google OAuth token

    # CORS
    ALLOWED_ORIGINS: str = "*"

    # Market Data & News APIs
    DART_API_KEY: Optional[str] = None
    NAVER_CLIENT_ID: Optional[str] = None
    NAVER_CLIENT_SECRET: Optional[str] = None
    NEWS_ALLOWED_DOMAINS: str = (
        "hankyung.com,mk.co.kr,edaily.co.kr,sedaily.com,chosun.com,donga.com,joins.com"
    )
    DATA_GO_KR_KEY: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def cors_origins(self) -> List[str]:
        if not self.ALLOWED_ORIGINS or self.ALLOWED_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def allowed_domains_list(self) -> List[str]:
        if not self.NEWS_ALLOWED_DOMAINS:
            return []
        return [d.strip() for d in self.NEWS_ALLOWED_DOMAINS.split(",") if d.strip()]


settings = Settings()
