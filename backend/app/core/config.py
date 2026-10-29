import os
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# 어느 폴더에서 실행해도 같은 .env / .local_db를 쓰도록 절대 경로로 고정
BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    # App
    PROJECT_NAME: str = "투자거울 (Investment Mirror)"
    VERSION: str = "1.1.0"
    API_V1_STR: str = "/api"
    # production 으로 두면 개발용 기능(DEV_MODE, 로컬 JSON 저장소)이 꺼집니다.
    # Render 에서는 RENDER 환경 변수가 자동으로 있으므로 따로 지정하지 않아도 운영 모드로 동작합니다.
    APP_ENV: str = "development"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Firebase
    FIREBASE_SERVICE_ACCOUNT_JSON: Optional[str] = None
    FIREBASE_CREDENTIALS_PATH: Optional[str] = None
    # 로컬 개발용 JSON 저장소 위치 (운영에서는 사용 불가)
    LOCAL_DB_DIR: str = str(ROOT_DIR / ".local_db")

    # Auth & Security
    ALLOWED_EMAIL: str = ""
    # 기본값은 꺼짐. 켜면 로그인 없이 모든 API가 열리므로 내 컴퓨터에서만 켜세요.
    DEV_MODE: bool = False

    # CORS
    ALLOWED_ORIGINS: str = "*"

    # Market Data & News APIs
    DART_API_KEY: Optional[str] = None
    NAVER_CLIENT_ID: Optional[str] = None
    NAVER_CLIENT_SECRET: Optional[str] = None
    NEWS_ALLOWED_DOMAINS: str = (
        "yna.co.kr,hankyung.com,mk.co.kr,edaily.co.kr,sedaily.com,mt.co.kr,"
        "chosun.com,donga.com,joongang.co.kr,hani.co.kr,khan.co.kr,biz.chosun.com,fnnews.com,newsis.com"
    )
    DATA_GO_KR_KEY: Optional[str] = None
    # 종목 등락률 - 코스피 등락률 차이가 이 값(%p) 이상이면 공시·뉴스를 찾아봅니다. (원인 판단 기준이 아님)
    INVESTIGATION_THRESHOLD_PCT: float = 2.0

    model_config = SettingsConfigDict(
        # 프로젝트 루트의 .env, backend/.env 둘 다 읽음 (뒤에 있는 파일이 우선)
        env_file=(str(ROOT_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def is_production(self) -> bool:
        return bool(os.getenv("RENDER")) or self.APP_ENV.strip().lower() == "production"

    @property
    def dev_mode_effective(self) -> bool:
        """운영 환경에서는 DEV_MODE 값과 관계없이 항상 꺼집니다."""
        return self.DEV_MODE and not self.is_production

    @property
    def openai_enabled(self) -> bool:
        key = (self.OPENAI_API_KEY or "").strip()
        return bool(key) and key.startswith("sk-") and not key.endswith("here")

    @property
    def cors_origins(self) -> List[str]:
        if not self.ALLOWED_ORIGINS or self.ALLOWED_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def allowed_domains_list(self) -> List[str]:
        if not self.NEWS_ALLOWED_DOMAINS:
            return []
        return [d.strip().lower() for d in self.NEWS_ALLOWED_DOMAINS.split(",") if d.strip()]


settings = Settings()
