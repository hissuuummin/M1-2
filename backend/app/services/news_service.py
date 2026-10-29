"""
등락 이유의 근거가 될 공시(DART)·뉴스(네이버)를 날짜 범위로 찾아 거르는 서비스.

원칙
- 날짜 범위는 코드가 정합니다: 전 거래일 장 마감(15:30) ~ 기준일 장 마감.
- 뉴스는 발행 시각이 범위 안이고, 허용한 언론사 도메인이며, 제목·요약에 종목명이 있는 기사만 씁니다.
- 결과가 없으면 빈 목록을 돌려주고, 왜 없는지(키 없음 / 범위 밖 / 실제로 없음)를 notes로 알려 줍니다.
- 어떤 경우에도 예시 기사나 링크를 만들어 내지 않습니다.
"""
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
import html
import io
import json
import logging
import os
import re
import tempfile
import time as time_mod
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
import zipfile

import httpx

from app.core.config import settings
from app.core.timeutil import KST, MARKET_CLOSE, now_kst, parse_date, today_kst

logger = logging.getLogger("investment_mirror.news_service")

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"
DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DART_CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
NEWS_LOOKBACK_DAYS = 7  # 대략 최근 5거래일
MAX_ITEMS = 5
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return html.unescape(_TAG_RE.sub("", text or "")).strip()


def _host_allowed(link: str, allowed_domains: Iterable[str]) -> bool:
    host = (urlparse(link).hostname or "").lower()
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in allowed_domains)


def investigation_window(base_date: date, prev_date: date) -> tuple:
    """전 거래일 15:30 ~ 기준일 15:30 (기준일이 오늘이고 장중이면 지금까지)."""
    start = datetime.combine(prev_date, MARKET_CLOSE, tzinfo=KST)
    end = datetime.combine(base_date, MARKET_CLOSE, tzinfo=KST)
    now = now_kst()
    return start, min(end, now)


def filter_news_items(
    items: List[Dict[str, Any]],
    stock_name: str,
    window_start: datetime,
    window_end: datetime,
    allowed_domains: List[str],
) -> List[Dict[str, Any]]:
    """네이버 뉴스 응답 item 목록에서 조건에 맞는 기사만 남깁니다. (네트워크 없이 테스트 가능)"""
    results = []
    for item in items:
        title = _clean(item.get("title", ""))
        desc = _clean(item.get("description", ""))
        link = item.get("originallink") or item.get("link") or ""
        try:
            published = parsedate_to_datetime(item.get("pubDate", ""))
        except (TypeError, ValueError):
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=KST)
        if not (window_start <= published <= window_end):
            continue
        if allowed_domains and not _host_allowed(link, allowed_domains):
            continue
        if stock_name not in title and stock_name not in desc:
            continue
        if not link.startswith("https://") and not link.startswith("http://"):
            continue
        results.append({
            "type": "news",
            "title": title,
            "source": (urlparse(link).hostname or "").replace("www.", ""),
            "link": link,
            "pub_date": published.astimezone(KST).strftime("%Y-%m-%d %H:%M"),
        })
    return results


def dedupe(items: List[Dict[str, Any]], limit: int = MAX_ITEMS) -> List[Dict[str, Any]]:
    """제목이 거의 같은 기사는 하나만 남깁니다 (공백·기호 제거 후 앞 20자 비교)."""
    seen = set()
    out = []
    for it in items:
        key = re.sub(r"[\W_]+", "", it.get("title", ""))[:20]
        if key and key in seen:
            continue
        seen.add(key)
        out.append(it)
        if len(out) >= limit:
            break
    return out


def parse_dart_list(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """DART list.json 응답을 출처 목록으로 바꿉니다. status 013은 '조회된 데이터 없음'."""
    status = payload.get("status")
    if status == "013":
        return []
    if status != "000":
        raise ValueError(f"DART status {status}: {payload.get('message', '')}")
    out = []
    for it in payload.get("list", []):
        rcept_no = str(it.get("rcept_no", ""))
        if not rcept_no.isdigit():
            continue
        rcept_dt = str(it.get("rcept_dt", ""))
        pub = f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:8]}" if len(rcept_dt) == 8 else rcept_dt
        out.append({
            "type": "disclosure",
            "title": (it.get("report_nm") or "").strip(),
            "source": "DART 전자공시",
            "link": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
            "pub_date": pub,
        })
    return out


class NewsService:
    _corp_codes: Dict[str, str] = {}
    _corp_codes_ts: float = 0.0
    _cache_file = os.path.join(tempfile.gettempdir(), "investment_mirror_dart_corp_codes.json")

    @classmethod
    async def _dart_corp_code(cls, stock_code: str) -> Optional[str]:
        """종목코드(6자리) → DART 고유번호(8자리). 7일간 메모리·임시파일에 캐시."""
        week = 7 * 24 * 3600
        if not cls._corp_codes and os.path.exists(cls._cache_file):
            try:
                if time_mod.time() - os.path.getmtime(cls._cache_file) < week:
                    with open(cls._cache_file, "r", encoding="utf-8") as f:
                        cls._corp_codes = json.load(f)
                    cls._corp_codes_ts = os.path.getmtime(cls._cache_file)
            except Exception:
                cls._corp_codes = {}

        if not cls._corp_codes or time_mod.time() - cls._corp_codes_ts > week:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(DART_CORP_CODE_URL, params={"crtfc_key": settings.DART_API_KEY})
                resp.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                xml_bytes = zf.read(zf.namelist()[0])
            mapping = {}
            for corp in ET.fromstring(xml_bytes).iter("list"):
                sc = (corp.findtext("stock_code") or "").strip()
                cc = (corp.findtext("corp_code") or "").strip()
                if sc and cc:
                    mapping[sc] = cc
            cls._corp_codes = mapping
            cls._corp_codes_ts = time_mod.time()
            try:
                with open(cls._cache_file, "w", encoding="utf-8") as f:
                    json.dump(mapping, f)
            except Exception:
                pass

        return cls._corp_codes.get(stock_code)

    @classmethod
    async def _search_dart(cls, stock_code: str, prev_date: date, base_date: date) -> List[Dict[str, Any]]:
        corp_code = await cls._dart_corp_code(stock_code)
        if not corp_code:
            return []
        params = {
            "crtfc_key": settings.DART_API_KEY,
            "corp_code": corp_code,
            "bgn_de": prev_date.strftime("%Y%m%d"),
            "end_de": base_date.strftime("%Y%m%d"),
            "page_count": 20,
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(DART_LIST_URL, params=params)
            resp.raise_for_status()
        return parse_dart_list(resp.json())

    @classmethod
    async def _search_naver(cls, stock_name: str, window_start: datetime, window_end: datetime) -> List[Dict[str, Any]]:
        headers = {
            "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET,
        }
        # 네이버 뉴스 API는 날짜 범위 검색이 없어서 최신순으로 받아 발행 시각으로 거릅니다.
        params = {"query": stock_name, "display": 100, "sort": "date"}
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(NAVER_NEWS_URL, headers=headers, params=params)
            resp.raise_for_status()
        return filter_news_items(
            resp.json().get("items", []), stock_name, window_start, window_end, settings.allowed_domains_list
        )

    @classmethod
    async def search_news_and_disclosures(
        cls,
        stock_name: str,
        stock_code: str,
        base_date: str,
        prev_date: str,
    ) -> Dict[str, Any]:
        """
        반환: {"items": [...], "checked": {"disclosure": bool, "news": bool}, "notes": [...]}
        checked가 False인 소스는 '확인하지 못함'이지 '이유 없음'이 아닙니다.
        """
        base = parse_date(base_date)
        prev = parse_date(prev_date)
        window_start, window_end = investigation_window(base, prev)

        items: List[Dict[str, Any]] = []
        checked = {"disclosure": False, "news": False}
        notes: List[str] = []

        if settings.DART_API_KEY:
            try:
                items.extend(await cls._search_dart(stock_code, prev, base))
                checked["disclosure"] = True
            except Exception as e:
                logger.warning("DART search failed: %s", type(e).__name__)
                notes.append("공시(DART) 조회에 실패했어요.")
        else:
            notes.append("DART API 키가 없어 공시는 확인하지 못했어요.")

        if not (settings.NAVER_CLIENT_ID and settings.NAVER_CLIENT_SECRET):
            notes.append("네이버 뉴스 API 키가 없어 뉴스는 확인하지 못했어요.")
        elif (today_kst() - base).days > NEWS_LOOKBACK_DAYS:
            notes.append("뉴스는 최근 5거래일까지만 찾을 수 있어서 이 날짜는 공시만 확인했어요.")
        else:
            try:
                items.extend(await cls._search_naver(stock_name, window_start, window_end))
                checked["news"] = True
            except Exception as e:
                logger.warning("Naver news search failed: %s", type(e).__name__)
                notes.append("뉴스 조회에 실패했어요.")

        return {
            "window": {
                "start": window_start.strftime("%Y-%m-%d %H:%M"),
                "end": window_end.strftime("%Y-%m-%d %H:%M"),
            },
            "items": dedupe(items),
            "checked": checked,
            "notes": notes,
        }
