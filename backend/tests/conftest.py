"""
테스트 공통 설정.

- 실제 .local_db나 Firestore를 건드리지 않도록 임시 폴더를 저장소로 씁니다.
- OpenAI 키는 비워 두고, 시세는 네트워크 없이 테스트용 시계열(fake_series)을 씁니다.
  fake_series는 테스트에서만 쓰는 값이며 앱 코드에는 들어가지 않습니다.
"""
import os
import sys
import tempfile
from datetime import date, timedelta

test_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(test_dir)
root_dir = os.path.dirname(backend_dir)
for p in [backend_dir, root_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

_TMP_DB = tempfile.mkdtemp(prefix="im_test_db_")
os.environ["LOCAL_DB_DIR"] = _TMP_DB
os.environ["DEV_MODE"] = "true"
os.environ["APP_ENV"] = "development"
os.environ["OPENAI_API_KEY"] = ""
os.environ["DART_API_KEY"] = ""
os.environ["NAVER_CLIENT_ID"] = ""
os.environ["NAVER_CLIENT_SECRET"] = ""
os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"] = ""
os.environ["FIREBASE_CREDENTIALS_PATH"] = ""
os.environ.pop("RENDER", None)

import pytest  # noqa: E402

from app.services import market_service  # noqa: E402


def fake_series(symbol: str, start: date, end: date):
    """평일마다 값이 조금씩 바뀌는 테스트용 시계열. KS11은 4000 근처, 종목은 70000 근처."""
    base = 4000.0 if symbol == market_service.KOSPI_SYMBOL else 70000.0
    out = {}
    d = start
    i = 0
    while d <= end:
        if d.weekday() < 5:
            out[d.strftime("%Y-%m-%d")] = round(base * (1 + 0.001 * (i % 7) - 0.002 * (i % 3)), 2)
            i += 1
        d += timedelta(days=1)
    return out


@pytest.fixture(autouse=True)
def offline_market(monkeypatch):
    monkeypatch.setattr(market_service, "_fetch_from_sources", fake_series)
    monkeypatch.setattr(market_service.MarketService, "_listing", {
        "ts": 10 ** 12, "name_to_code": {"삼성전자": "005930", "카카오": "035720"},
        "code_to_name": {"005930": "삼성전자", "035720": "카카오"},
    })
    yield
