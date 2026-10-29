"""
시장 데이터(코스피 지수, 종목 종가) 조회 서비스.

- 1순위: FinanceDataReader
- 2순위: 금융위원회 주식시세·지수시세 API (공공데이터포털, DATA_GO_KR_KEY 필요)
  다음 영업일 오후에 갱신되므로 과거 데이터(그래프·복기)에는 쓸 수 있지만 당일 값은 없습니다.
- 두 곳 모두 실패하면 값을 지어내지 않고 MarketDataError를 냅니다.

조회한 가격은 Firestore `prices/{심볼}` 문서에 캐시합니다.
"""
from datetime import date, datetime, timedelta, timezone
import logging
import time as time_mod
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from app.core.config import settings
from app.core.firebase import get_firestore_client
from app.core.timeutil import (
    MARKET_CLOSE,
    fmt_date,
    is_weekend,
    label_kr,
    now_kst,
    parse_date,
    today_kst,
)
from app.models.schemas import StockPricePoint, StockPricesResponse

logger = logging.getLogger("investment_mirror.market_service")

KOSPI_SYMBOL = "KS11"
CACHE_COLLECTION = "prices"
CACHE_FRESH_SECONDS = 30 * 60  # 오늘 날짜가 포함된 구간은 30분마다 다시 받음
DATA_GO_KR_STOCK_URL = "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo"
DATA_GO_KR_INDEX_URL = "https://apis.data.go.kr/1160100/service/GetMarketIndexInfoService/getStockMarketIndex"

# 종목 목록을 받지 못할 때만 쓰는 최소 매핑
STATIC_STOCK_MAP = {
    "삼성전자": "005930",
    "SK하이닉스": "000660",
    "LG에너지솔루션": "373220",
    "삼성바이오로직스": "207940",
    "현대차": "005380",
    "기아": "000270",
    "셀트리온": "068270",
    "KB금융": "105560",
    "NAVER": "035420",
    "네이버": "035420",
    "카카오": "035720",
    "신한지주": "055550",
    "POSCO홀딩스": "005490",
    "포스코홀딩스": "005490",
    "에코프로비엠": "247540",
    "알테오젠": "196170",
}


class MarketDataError(Exception):
    """시장 데이터를 가져오지 못했을 때 (사용자에게 보여줄 메시지를 담음)"""


# ---------------------------------------------------------------------------
# 데이터 소스
# ---------------------------------------------------------------------------

def _fetch_fdr(symbol: str, start: date, end: date) -> Dict[str, float]:
    try:
        import FinanceDataReader as fdr  # noqa: N813
    except ImportError as e:
        raise MarketDataError("FinanceDataReader가 설치되어 있지 않아요.") from e

    df = fdr.DataReader(symbol, fmt_date(start), fmt_date(end))
    out: Dict[str, float] = {}
    if df is None or df.empty or "Close" not in df.columns:
        return out
    for idx, close in df["Close"].items():
        try:
            value = float(close)
        except (TypeError, ValueError):
            continue
        if value > 0:
            out[idx.strftime("%Y-%m-%d")] = value
    return out


def _data_go_kr_items(url: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not settings.DATA_GO_KR_KEY:
        raise MarketDataError("공공데이터포털 키(DATA_GO_KR_KEY)가 없어요.")
    base = {"serviceKey": settings.DATA_GO_KR_KEY, "resultType": "json", "numOfRows": 1000, "pageNo": 1}
    resp = requests.get(url, params={**base, **params}, timeout=10)
    resp.raise_for_status()
    body = resp.json().get("response", {}).get("body", {})
    items = (body.get("items") or {}).get("item") or []
    if isinstance(items, dict):
        items = [items]
    return items


def _fetch_data_go_kr(symbol: str, start: date, end: date) -> Dict[str, float]:
    period = {"beginBasDt": start.strftime("%Y%m%d"), "endBasDt": end.strftime("%Y%m%d")}
    if symbol == KOSPI_SYMBOL:
        items = _data_go_kr_items(DATA_GO_KR_INDEX_URL, {**period, "idxNm": "코스피"})
        items = [it for it in items if it.get("idxNm") == "코스피"]
    else:
        items = _data_go_kr_items(DATA_GO_KR_STOCK_URL, {**period, "likeSrtnCd": symbol})
        items = [it for it in items if str(it.get("srtnCd", "")).zfill(6) == symbol]

    out: Dict[str, float] = {}
    for it in items:
        try:
            d = datetime.strptime(str(it["basDt"]), "%Y%m%d").strftime("%Y-%m-%d")
            value = float(str(it["clpr"]).replace(",", ""))
        except (KeyError, ValueError):
            continue
        if value > 0:
            out[d] = value
    return out


SOURCES: List[Tuple[str, Callable[[str, date, date], Dict[str, float]]]] = [
    ("FinanceDataReader", _fetch_fdr),
    ("금융위원회 시세 API", _fetch_data_go_kr),
]


def _fetch_from_sources(symbol: str, start: date, end: date) -> Dict[str, float]:
    errors = []
    for name, fn in SOURCES:
        try:
            series = fn(symbol, start, end)
            if series:
                return series
            errors.append(f"{name}: 빈 결과")
        except MarketDataError as e:
            errors.append(f"{name}: {e}")
        except Exception as e:  # 네트워크 차단, 형식 변경 등
            errors.append(f"{name}: {type(e).__name__}")
            logger.warning("Market source %s failed for %s: %s", name, symbol, e)
    logger.warning("All market sources failed for %s (%s~%s): %s", symbol, start, end, errors)
    raise MarketDataError("시세 데이터를 가져오지 못했어요. 잠시 후 다시 시도해 주세요.")


# ---------------------------------------------------------------------------
# 캐시 + 시계열 조회
# ---------------------------------------------------------------------------

def get_series(symbol: str, start: date, end: date) -> Dict[str, float]:
    """symbol: 'KS11'(코스피) 또는 6자리 종목코드. {날짜: 종가} (날짜 오름차순 정렬 아님)"""
    today = today_kst()
    end = min(end, today)
    if start > end:
        return {}

    doc_ref = get_firestore_client().collection(CACHE_COLLECTION).document(symbol)
    cached = None
    try:
        snap = doc_ref.get()
        cached = snap.to_dict() if snap.exists else None
    except Exception as e:
        logger.warning("Price cache read failed for %s: %s", symbol, type(e).__name__)

    if cached:
        c_start = cached.get("range_start", "9999-12-31")
        c_end = cached.get("range_end", "0000-01-01")
        fetched_at = float(cached.get("fetched_at_ts", 0))
        covers = c_start <= fmt_date(start) and c_end >= fmt_date(end)
        stale_today = end >= today and (time_mod.time() - fetched_at) > CACHE_FRESH_SECONDS
        if covers and not stale_today:
            return {d: v for d, v in cached.get("series", {}).items() if fmt_date(start) <= d <= fmt_date(end)}

    fetch_start, fetch_end = start, end
    merged: Dict[str, float] = {}
    if cached:
        fetch_start = min(start, parse_date(cached.get("range_start", fmt_date(start))))
        fetch_end = max(end, parse_date(cached.get("range_end", fmt_date(end))))
        merged.update(cached.get("series", {}))

    fresh = _fetch_from_sources(symbol, fetch_start, fetch_end)
    merged.update(fresh)

    try:
        doc_ref.set({
            "symbol": symbol,
            "series": merged,
            "range_start": fmt_date(fetch_start),
            "range_end": fmt_date(fetch_end),
            "fetched_at_ts": time_mod.time(),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.warning("Price cache write failed for %s: %s", symbol, type(e).__name__)

    return {d: v for d, v in merged.items() if fmt_date(start) <= d <= fmt_date(end)}


def _stored_kospi(start: date, end: date) -> Dict[str, float]:
    """data 컬렉션에 저장된 코스피 값 (사용자가 직접 고친 값도 포함)."""
    out: Dict[str, float] = {}
    for d in get_firestore_client().collection("data").stream():
        data = d.to_dict() or {}
        dt = data.get("date", d.id)
        if fmt_date(start) <= dt <= fmt_date(end):
            try:
                out[dt] = float(data["value"])
            except (KeyError, TypeError, ValueError):
                continue
    return out


def kospi_closes(start: date, end: date) -> Dict[str, float]:
    """코스피 종가. 저장된 값(data 컬렉션)을 우선 쓰고, 없는 날만 외부에서 받습니다."""
    stored = _stored_kospi(start, end)
    try:
        fetched = get_series(KOSPI_SYMBOL, start, end)
    except MarketDataError:
        if stored:
            return stored
        raise
    return {**fetched, **stored}


def _last_on_or_before(series: Dict[str, float], target: str) -> Optional[Tuple[str, float]]:
    keys = sorted(d for d in series if d <= target)
    return (keys[-1], series[keys[-1]]) if keys else None


def _previous(series: Dict[str, float], target: str) -> Optional[Tuple[str, float]]:
    keys = sorted(d for d in series if d < target)
    return (keys[-1], series[keys[-1]]) if keys else None


def _pct(curr: float, prev: float) -> float:
    return round((curr - prev) / prev * 100, 2) if prev else 0.0


# ---------------------------------------------------------------------------
# 서비스
# ---------------------------------------------------------------------------

class MarketService:
    _listing: Dict[str, Any] = {"ts": 0.0, "name_to_code": {}, "code_to_name": {}}

    @classmethod
    def _load_listing(cls) -> None:
        if time_mod.time() - cls._listing["ts"] < 24 * 3600 and cls._listing["name_to_code"]:
            return
        try:
            import FinanceDataReader as fdr  # noqa: N813
            df = fdr.StockListing("KRX")
            name_to_code = {}
            code_to_name = {}
            for _, row in df.iterrows():
                code = str(row.get("Code", "")).zfill(6)
                name = str(row.get("Name", "")).strip()
                if code.isdigit() and name:
                    name_to_code[name] = code
                    name_to_code[name.upper()] = code
                    code_to_name[code] = name
            if name_to_code:
                cls._listing = {"ts": time_mod.time(), "name_to_code": name_to_code, "code_to_name": code_to_name}
        except Exception as e:
            logger.warning("Stock listing unavailable, using static map: %s", type(e).__name__)
            cls._listing["ts"] = time_mod.time()  # 실패해도 매 요청마다 재시도하지 않도록

    @classmethod
    def get_stock_code(cls, name_or_code: str) -> Optional[str]:
        clean = (name_or_code or "").strip()
        if clean.isdigit() and len(clean) == 6:
            return clean
        if clean in STATIC_STOCK_MAP:
            return STATIC_STOCK_MAP[clean]
        cls._load_listing()
        n2c = cls._listing["name_to_code"]
        return n2c.get(clean) or n2c.get(clean.upper()) or n2c.get(clean.replace(" ", ""))

    @classmethod
    def get_stock_name(cls, code: str) -> str:
        clean = (code or "").strip().zfill(6)
        for name, c in STATIC_STOCK_MAP.items():
            if c == clean and name not in ("네이버", "포스코홀딩스"):
                return name
        cls._load_listing()
        return cls._listing["code_to_name"].get(clean, clean)

    # --- 그래프 -------------------------------------------------------------

    @classmethod
    def get_stock_and_kospi_comparison(
        cls,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> StockPricesResponse:
        """종목·코스피 종가를 같은 날짜끼리 맞추고, 기간 첫 공통 거래일을 100으로 정규화합니다."""
        clean_code = (cls.get_stock_code(code) or "").zfill(6)
        if not clean_code.isdigit():
            raise MarketDataError("종목 코드를 확인해 주세요.")

        end = parse_date(end_date) if end_date else today_kst()
        start = parse_date(start_date) if start_date else end - timedelta(days=365)

        stock = get_series(clean_code, start, end)
        kospi = kospi_closes(start, end)
        common = sorted(set(stock) & set(kospi))
        if not common:
            raise MarketDataError("해당 기간에 종목과 코스피 가격이 함께 있는 날이 없어요.")

        first_stock, first_kospi = stock[common[0]], kospi[common[0]]
        points = [
            StockPricePoint(
                date=d,
                stock_close=stock[d],
                kospi_close=kospi[d],
                stock_indexed=round(stock[d] / first_stock * 100, 2),
                kospi_indexed=round(kospi[d] / first_kospi * 100, 2),
            )
            for d in common
        ]

        trades = []
        for doc in get_firestore_client().collection("data").stream():
            data = doc.to_dict() or {}
            dt = data.get("date", doc.id)
            if not (fmt_date(start) <= dt <= fmt_date(end)):
                continue
            for t in data.get("trades", []):
                if str(t.get("code", "")).zfill(6) == clean_code:
                    trades.append({**t, "date": dt})
        trades.sort(key=lambda t: t["date"])

        return StockPricesResponse(
            code=clean_code,
            name=cls.get_stock_name(clean_code),
            start_date=common[0],
            end_date=common[-1],
            data=points,
            trades=trades,
        )

    # --- 등락 비교 ----------------------------------------------------------

    @classmethod
    def get_stock_change(cls, name_or_code: str, target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        기준일 종목·코스피 등락률과 그 차이. 기준일은 코드가 정합니다(휴장일이면 직전 거래일).
        실패하면 {"error": ...}를 돌려주고 숫자를 지어내지 않습니다.
        """
        code = cls.get_stock_code(name_or_code)
        if not code:
            return {"error": f"'{name_or_code}' 종목을 찾지 못했어요. 종목명이나 6자리 코드를 확인해 주세요."}

        today = today_kst()
        try:
            target = min(parse_date(target_date), today) if target_date else today
        except ValueError:
            return {"error": "날짜는 YYYY-MM-DD 형식이어야 해요."}

        start = target - timedelta(days=20)
        try:
            stock = get_series(code, start, target)
            kospi = kospi_closes(start, target)
        except MarketDataError as e:
            return {"error": str(e)}

        base = _last_on_or_before(stock, fmt_date(target))
        if not base:
            return {"error": "기준일 근처의 종목 가격을 찾지 못했어요."}
        base_date, base_close = base
        prev = _previous(stock, base_date)
        if not prev or base_date not in kospi:
            return {"error": "등락률을 계산할 이전 거래일 데이터가 부족해요."}
        prev_date, prev_close = prev
        k_prev = kospi.get(prev_date) or (_previous(kospi, base_date) or (None, None))[1]
        if not k_prev:
            return {"error": "코스피 이전 거래일 데이터를 찾지 못했어요."}

        stock_pct = _pct(base_close, prev_close)
        kospi_pct = _pct(kospi[base_date], k_prev)
        diff = round(stock_pct - kospi_pct, 2)
        now = now_kst()
        is_intraday = base_date == fmt_date(now.date()) and now.time() < MARKET_CLOSE
        threshold = settings.INVESTIGATION_THRESHOLD_PCT
        needs = abs(diff) >= threshold

        return {
            "date": base_date,
            "date_label": label_kr(parse_date(base_date)),
            "prev_date": prev_date,
            "requested_date": fmt_date(target),
            "is_intraday": is_intraday,
            "stock_name": cls.get_stock_name(code),
            "stock_code": code,
            "stock_close": base_close,
            "stock_pct": stock_pct,
            "kospi_pct": kospi_pct,
            "diff_pct": diff,
            "threshold_pct": threshold,
            "is_significant": needs,
            "note": (
                f"차이 {threshold}%p는 공시·뉴스를 찾아볼지 정하는 조사 시작 기준일 뿐, 원인 판단이 아니에요. "
                "업종 전체가 함께 움직였을 가능성도 있어요."
            ),
        }

    @classmethod
    def get_stock_close(
        cls, code_or_name: str, target_date: str, buy_price: Optional[float] = None
    ) -> Dict[str, Any]:
        code = cls.get_stock_code(code_or_name)
        if not code:
            return {"error": f"'{code_or_name}' 종목을 찾지 못했어요."}
        try:
            target = parse_date(target_date)
        except ValueError:
            return {"error": "날짜는 YYYY-MM-DD 형식이어야 해요."}

        today = today_kst()
        try:
            series = get_series(code, min(target, today) - timedelta(days=15), today)
        except MarketDataError as e:
            return {"error": str(e)}

        on_date = _last_on_or_before(series, fmt_date(target))
        latest = _last_on_or_before(series, fmt_date(today))
        if not on_date or not latest:
            return {"error": "해당 날짜의 종가를 찾지 못했어요."}

        result: Dict[str, Any] = {
            "stock_name": cls.get_stock_name(code),
            "stock_code": code,
            "date": on_date[0],
            "close": on_date[1],
            "latest_date": latest[0],
            "latest_close": latest[1],
            "change_since_pct": _pct(latest[1], on_date[1]),
        }
        if buy_price and buy_price > 0:
            result["buy_price"] = buy_price
            result["return_vs_buy_pct"] = _pct(latest[1], buy_price)
        return result

    # --- 코스피 저장 데이터 ---------------------------------------------------

    @classmethod
    def kospi_close_on(cls, d: date) -> Optional[float]:
        """그 날짜가 거래일이면 코스피 종가, 아니면 None."""
        series = get_series(KOSPI_SYMBOL, d - timedelta(days=7), d)
        return series.get(fmt_date(d))

    @classmethod
    def latest_kospi(cls) -> Optional[Tuple[str, float]]:
        today = today_kst()
        series = get_series(KOSPI_SYMBOL, today - timedelta(days=10), today)
        return _last_on_or_before(series, fmt_date(today))

    @classmethod
    def sync_kospi(cls, days_back: int = 30) -> Dict[str, int]:
        """
        코스피 실제 종가로 data 컬렉션을 채웁니다.
        - 없는 거래일은 새로 만들고
        - 자동으로 만든 문서(source가 sync/trade_entry)는 값이 다르면 실제 종가로 고칩니다.
        - 직접 입력한 값(manual)은 건드리지 않습니다.
        - 오늘은 장 마감(15:30) 전이면 넣지 않습니다.
        """
        from app.services.data_service import DataService  # 순환 import 방지

        today = today_kst()
        records = {r["date"]: r for r in DataService.get_all_records()}
        start = today - timedelta(days=days_back)
        series = get_series(KOSPI_SYMBOL, start, today)
        now = now_kst()
        created = updated = 0
        for d, close in sorted(series.items()):
            if d == fmt_date(today) and now.time() < MARKET_CLOSE:
                continue
            if is_weekend(parse_date(d)):
                continue
            existing = records.get(d)
            if existing is None:
                DataService.create_market_record(d, close)
                created += 1
            elif existing.get("source") in ("sync", "trade_entry") and abs(float(existing.get("value", 0)) - close) > 0.005:
                DataService.set_market_value(d, close)
                updated += 1
        return {"created": created, "updated": updated}
