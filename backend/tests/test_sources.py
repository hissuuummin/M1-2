"""시세·뉴스·공시·파일·캡처 처리에서 값을 지어내지 않는지 확인하는 테스트 (네트워크 없음)."""
from datetime import datetime, timedelta

import pytest

from app.core.timeutil import KST, fmt_date, today_kst
from app.services import market_service
from app.services.importer_service import find_columns, parse_number, parse_side, parse_trade_date
from app.services.market_service import MarketDataError, MarketService
from app.services.news_service import dedupe, filter_news_items, parse_dart_list
from app.services.vision_service import normalize_candidates


# --- 시세 ------------------------------------------------------------------

def test_stock_change_uses_last_trading_day_for_weekend():
    d = today_kst() - timedelta(days=14)
    while d.weekday() != 5:  # 토요일
        d -= timedelta(days=1)
    res = MarketService.get_stock_change("삼성전자", fmt_date(d))
    friday = fmt_date(d - timedelta(days=1))
    assert res["date"] == friday
    assert res["date_label"].endswith("(금)")
    assert res["diff_pct"] == round(res["stock_pct"] - res["kospi_pct"], 2)


def test_stock_change_unknown_stock_returns_error():
    res = MarketService.get_stock_change("없는종목이름")
    assert "error" in res


def test_market_failure_raises_instead_of_inventing(monkeypatch):
    def boom(symbol, start, end):
        raise MarketDataError("시세 데이터를 가져오지 못했어요.")

    monkeypatch.setattr(market_service, "_fetch_from_sources", boom)
    res = MarketService.get_stock_change("035720", fmt_date(today_kst() - timedelta(days=400)))
    assert "error" in res
    with pytest.raises(MarketDataError):
        MarketService.get_stock_and_kospi_comparison("035720", "2020-01-01", "2020-02-01")


# --- 뉴스 ------------------------------------------------------------------

def _naver_item(title, link, when):
    return {
        "title": title, "description": "", "originallink": link, "link": link,
        "pubDate": when.strftime("%a, %d %b %Y %H:%M:%S +0900"),
    }


def test_news_filter_window_domain_and_name():
    start = datetime(2026, 10, 23, 15, 30, tzinfo=KST)
    end = datetime(2026, 10, 24, 15, 30, tzinfo=KST)
    items = [
        _naver_item("[특징주] 삼성전자 급락", "https://www.hankyung.com/a/1", datetime(2026, 10, 24, 9, 5)),
        _naver_item("삼성전자 지난주 실적", "https://www.mk.co.kr/n/2", datetime(2026, 10, 20, 9, 0)),   # 범위 밖
        _naver_item("삼성전자 광고 기사", "https://spam-blog.example.com/3", datetime(2026, 10, 24, 10, 0)),  # 도메인 밖
        _naver_item("반도체 업황 점검", "https://www.mk.co.kr/n/4", datetime(2026, 10, 24, 11, 0)),       # 종목명 없음
        _naver_item("삼성전자 외국인 매도", "https://evilhankyung.com/5", datetime(2026, 10, 24, 11, 0)),  # 비슷한 가짜 도메인
    ]
    res = filter_news_items(items, "삼성전자", start, end, ["hankyung.com", "mk.co.kr"])
    assert [r["link"] for r in res] == ["https://www.hankyung.com/a/1"]
    assert res[0]["pub_date"] == "2026-10-24 09:05"


def test_dedupe_merges_similar_titles():
    items = [{"title": "삼성전자, 3분기 실적 발표…영업익 증가"}, {"title": "삼성전자 3분기 실적 발표 영업익 증가!"},
             {"title": "카카오 신고가"}]
    assert len(dedupe(items)) == 2


def test_parse_dart_list():
    payload = {"status": "000", "list": [{"rcept_no": "20261024000123", "report_nm": "주요사항보고서", "rcept_dt": "20261024"}]}
    res = parse_dart_list(payload)
    assert res[0]["link"].endswith("rcpNo=20261024000123")
    assert res[0]["pub_date"] == "2026-10-24"
    assert parse_dart_list({"status": "013"}) == []


# --- 거래내역 파일 ----------------------------------------------------------

def test_find_columns_prefers_exact_names():
    cols = find_columns(["종목코드", "종목명", "매매구분", "체결수량", "체결단가", "체결일자"])
    assert cols["name"] == "종목명"
    assert cols["code"] == "종목코드"
    assert cols["date"] == "체결일자"


def test_parsers():
    assert parse_number("71,500원") == 71500.0
    assert parse_side("현금매도") == "sell"
    assert parse_side("입금") is None
    assert parse_trade_date("2026.10.24") == "2026-10-24"
    assert parse_trade_date("20261024") == "2026-10-24"


# --- 캡처 ------------------------------------------------------------------

def test_capture_candidates_are_not_invented():
    raw = [
        {"side": "buy", "name": "삼성전자", "code": None, "qty": "10", "price": "71,500", "date": None},
        {"side": "buy", "name": "카카오", "qty": None, "price": 40000},  # 수량 없음 → 버림
        {"side": "hold", "name": "카카오", "qty": 1, "price": 1},        # 매매 아님 → 버림
    ]
    res = normalize_candidates(raw)
    assert len(res) == 1
    assert res[0]["code"] == "005930"
    assert res[0]["price"] == 71500.0
    assert "date" in res[0]["needs_check"]
