"""
한국 시간(KST) 관련 공통 함수.

서버(Render)는 UTC로 돌기 때문에 "오늘", "장 마감" 같은 판단은 항상 이 모듈을 거칩니다.
한국은 서머타임이 없어서 고정 오프셋(+09:00)을 씁니다. (Windows에서 tzdata 없이도 동작)
"""
from datetime import date, datetime, time, timedelta, timezone

KST = timezone(timedelta(hours=9))
MARKET_CLOSE = time(15, 30)
WEEKDAYS_KR = ["월", "화", "수", "목", "금", "토", "일"]


def now_kst() -> datetime:
    return datetime.now(KST)


def today_kst() -> date:
    return now_kst().date()


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def fmt_date(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def label_kr(d: date) -> str:
    """2026-10-24 -> '10월 24일(금)'"""
    return f"{d.month}월 {d.day}일({WEEKDAYS_KR[d.weekday()]})"


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def market_closed_today() -> bool:
    """오늘 장이 끝났는지(15:30 이후 또는 주말)."""
    now = now_kst()
    return is_weekend(now.date()) or now.time() >= MARKET_CLOSE
