from datetime import timedelta

from fastapi.testclient import TestClient

from app.core.timeutil import fmt_date, today_kst
from app.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer dev-token"}


def last_weekday(days_ago: int) -> str:
    d = today_kst() - timedelta(days=days_ago)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return fmt_date(d)


def next_saturday_in_past() -> str:
    d = today_kst() - timedelta(days=7)
    while d.weekday() != 5:
        d -= timedelta(days=1)
    return fmt_date(d)


def test_health_reports_dev_auth_mode():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["auth_mode"] == "dev"
    assert data["ai_enabled"] is False


def test_data_crud_and_duplicate_409():
    test_date = "2024-01-02"
    client.delete(f"/api/data/{test_date}", headers=AUTH)

    create_res = client.post("/api/data", json={"date": test_date, "value": 2550.0, "memo": "테스트"}, headers=AUTH)
    assert create_res.status_code == 201

    dup_res = client.post("/api/data", json={"date": test_date, "value": 2560.0}, headers=AUTH)
    assert dup_res.status_code == 409

    summary_res = client.get("/api/data/summary", headers=AUTH)
    assert summary_res.status_code == 200
    assert "trend" in summary_res.json()

    update_res = client.put(f"/api/data/{test_date}", json={"value": 2580.0, "memo": "수정"}, headers=AUTH)
    assert update_res.status_code == 200
    assert update_res.json()["value"] == 2580.0

    assert client.delete(f"/api/data/{test_date}", headers=AUTH).status_code == 200
    assert client.delete(f"/api/data/{test_date}", headers=AUTH).status_code == 404


def test_validation_errors():
    future = fmt_date(today_kst() + timedelta(days=3))
    assert client.post("/api/data", json={"date": future, "value": 1.0}, headers=AUTH).status_code == 422
    assert client.post("/api/data", json={"date": "2024-01-03", "value": -1}, headers=AUTH).status_code == 422
    assert client.post("/api/chat", json={"message": ""}, headers=AUTH).status_code == 422


def test_conversations_flow():
    create_res = client.post(
        "/api/conversations",
        json={"title": "테스트 대화", "messages": [{"role": "user", "content": "안녕"}]},
        headers=AUTH
    )
    assert create_res.status_code == 201
    conv_id = create_res.json()["id"]

    items = client.get("/api/conversations", headers=AUTH).json()
    assert any(c["id"] == conv_id for c in items)
    assert "messages" not in items[0]

    detail = client.get(f"/api/conversations/{conv_id}", headers=AUTH).json()
    assert len(detail["messages"]) >= 1

    assert client.delete(f"/api/conversations/{conv_id}", headers=AUTH).status_code == 200


def test_chat_without_openai_key_is_honest():
    res = client.post("/api/chat", json={"message": "오늘 삼성전자 왜 떨어졌어?"}, headers=AUTH)
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "offline"
    assert "AI가 연결되어 있지 않아" in data["reply"]
    assert data["sources"] == []          # 출처를 지어내지 않음
    assert data["pending_trades"] == []
    # 자동 저장 확인
    conv = client.get(f"/api/conversations/{data['conversation_id']}", headers=AUTH).json()
    assert len(conv["messages"]) == 2


def test_sync_uses_market_data():
    res = client.post("/api/data/sync?days=20", headers=AUTH)
    assert res.status_code == 200
    records = client.get("/api/data", headers=AUTH).json()
    synced = [r for r in records if r["source"] == "sync"]
    assert len(synced) >= 10
    assert all(3900 < r["value"] < 4100 for r in synced)  # 테스트 시계열 값이 그대로 들어감


def test_trade_crud_reason_timing_and_two_trades_same_day():
    test_date = last_weekday(10)
    client.delete(f"/api/data/{test_date}", headers=AUTH)

    trade = {"side": "buy", "name": "삼성전자", "code": "005930", "qty": 10, "price": 70000.0, "reason": "성장성"}
    add_res = client.post(f"/api/data/{test_date}/trades", json=trade, headers=AUTH)
    assert add_res.status_code == 201
    first = add_res.json()
    # 오늘 과거 날짜 매매에 이유를 남겼으므로 '이후 회상'
    assert first["reason_timing"] == "이후 회상"

    # 같은 날 두 번째 매매도 저장되어야 함 (409 아님)
    second = client.post(
        f"/api/data/{test_date}/trades",
        json={"side": "buy", "name": "카카오", "code": "035720", "qty": 3, "price": 40000.0},
        headers=AUTH,
    )
    assert second.status_code == 201
    assert second.json()["reason_timing"] is None

    # 같은 거래 id 재전송은 중복 저장되지 않음
    again = client.post(f"/api/data/{test_date}/trades", json={**trade, "id": first["id"]}, headers=AUTH)
    assert again.status_code == 201
    record = [r for r in client.get("/api/data", headers=AUTH).json() if r["date"] == test_date][0]
    assert len(record["trades"]) == 2
    # 새 날짜 문서의 코스피 값은 시세에서 가져온 값 (예전처럼 2600 고정값이 아님)
    assert 3900 < record["value"] < 4100

    up_res = client.put(f"/api/data/{test_date}/trades/{first['id']}", json={"reason": "시장 흐름"}, headers=AUTH)
    assert up_res.status_code == 200
    assert up_res.json()["reason"] == "시장 흐름"

    bad_reason = client.put(f"/api/data/{test_date}/trades/{first['id']}", json={"reason": "감"}, headers=AUTH)
    assert bad_reason.status_code == 422

    assert client.delete(f"/api/data/{test_date}/trades/{first['id']}", headers=AUTH).status_code == 200
    client.delete(f"/api/data/{test_date}", headers=AUTH)


def test_trade_on_weekend_is_rejected():
    sat = next_saturday_in_past()
    res = client.post(
        f"/api/data/{sat}/trades",
        json={"side": "buy", "name": "삼성전자", "code": "005930", "qty": 1, "price": 70000.0},
        headers=AUTH,
    )
    assert res.status_code == 422


def test_review_pending_and_done():
    test_date = last_weekday(12)
    client.delete(f"/api/data/{test_date}", headers=AUTH)
    t = client.post(
        f"/api/data/{test_date}/trades",
        json={"side": "buy", "name": "삼성전자", "code": "005930", "qty": 5, "price": 69000.0, "reason": "가격 하락"},
        headers=AUTH,
    ).json()

    pending = client.get("/api/review/pending", headers=AUTH).json()
    item = next(p for p in pending if p["trade_id"] == t["id"])
    assert item["review_type"] == "7d"
    assert item["stock_change_vs_price"] is not None
    assert "가격 하락" in item["suggested_question"]

    done = client.post(f"/api/review/{t['id']}/done?review_type=7d", headers=AUTH)
    assert done.status_code == 200
    pending_after = client.get("/api/review/pending", headers=AUTH).json()
    assert all(p["trade_id"] != t["id"] for p in pending_after)
    client.delete(f"/api/data/{test_date}", headers=AUTH)


def test_stock_comparison_is_indexed_to_100():
    res = client.get("/api/stocks/005930/prices", headers=AUTH)
    assert res.status_code == 200
    data = res.json()
    assert data["code"] == "005930"
    assert data["data"][0]["stock_indexed"] == 100.0
    assert data["data"][0]["kospi_indexed"] == 100.0


def test_statistics_and_export():
    stats = client.get("/api/data/statistics", headers=AUTH)
    assert stats.status_code == 200
    assert "volatility_daily" in stats.json()

    csv_res = client.get("/api/data/export?format=csv", headers=AUTH)
    assert csv_res.status_code == 200
    assert "date,kospi_value" in csv_res.text

    json_res = client.get("/api/data/export?format=json", headers=AUTH)
    assert isinstance(json_res.json(), list)


def test_unknown_api_path_returns_404_not_index_html():
    res = client.get("/api/does-not-exist", headers=AUTH)
    assert res.status_code == 404
