import os

from app.core.config import Settings


def test_dev_mode_is_off_by_default(monkeypatch):
    monkeypatch.delenv("DEV_MODE", raising=False)
    s = Settings(_env_file=None)
    assert s.DEV_MODE is False
    assert s.dev_mode_effective is False


def test_dev_mode_is_forced_off_on_render(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    s = Settings(_env_file=None, DEV_MODE=True)
    assert s.is_production is True
    assert s.dev_mode_effective is False


def test_frontend_path_traversal_is_blocked():
    from app.main import _frontend_dir, _safe_frontend_path

    assert _safe_frontend_path("index.html") == os.path.join(_frontend_dir, "index.html")
    assert _safe_frontend_path("components/chat.js") is not None
    assert _safe_frontend_path("../backend/.env") is None
    assert _safe_frontend_path("../backend/app/core/config.py") is None
    assert _safe_frontend_path("..\\backend\\.env") is None or os.sep == "/"
    assert _safe_frontend_path(".env") is None


def test_traversal_request_does_not_leak_files():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    for path in ["/%2e%2e/backend/app/core/config.py", "/..%2Fbackend%2Fapp%2Fcore%2Fconfig.py"]:
        res = client.get(path)
        assert "BaseSettings" not in res.text
