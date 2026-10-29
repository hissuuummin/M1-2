from datetime import timedelta
import logging
from typing import Dict, List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.auth import get_current_user
from app.core.timeutil import fmt_date, parse_date, today_kst
from app.models.schemas import PendingReviewItem, TradeUpdate
from app.services.data_service import DataService
from app.services.market_service import MarketDataError, get_series

logger = logging.getLogger("investment_mirror.review")
router = APIRouter(prefix="/review", tags=["Review"])


def _pct(curr: float, base: float) -> float:
    return round((curr - base) / base * 100, 2) if base else 0.0


def _latest_stock_close(code: str, since: str, cache: Dict[str, Optional[tuple]]) -> Optional[tuple]:
    """매매일 이후 최신 종가 (날짜, 값). 실패하면 None — 값을 지어내지 않습니다."""
    if code in cache:
        return cache[code]
    result = None
    try:
        today = today_kst()
        series = get_series(code, min(parse_date(since), today - timedelta(days=10)), today)
        if series:
            last = max(series)
            result = (last, series[last])
    except MarketDataError:
        result = None
    except Exception as e:
        logger.warning("Stock price lookup failed for review (%s): %s", code, type(e).__name__)
    cache[code] = result
    return result


@router.get("/pending", response_model=List[PendingReviewItem])
def get_pending_reviews(current_user: dict = Depends(get_current_user)):
    """
    7일·30일이 지난 미완료 매매를 돌려줍니다. 30일이 지난 매매는 30일 복기로만 보여 줍니다.
    이후 변화는 서버가 계산한 값만 쓰고, 질문 문장은 기록과 계산값을 채운 틀로 만듭니다.
    """
    records = DataService.get_all_records()
    if not records:
        return []

    sorted_records = sorted(records, key=lambda x: x["date"])
    latest_kospi = float(sorted_records[-1]["value"])
    today = today_kst()
    price_cache: Dict[str, Optional[tuple]] = {}
    pending_items: List[PendingReviewItem] = []

    for r in sorted_records:
        r_date_str = r["date"]
        days_passed = (today - parse_date(r_date_str)).days
        if days_passed < 7:
            continue
        kospi_then = float(r["value"])
        k_diff = _pct(latest_kospi, kospi_then)

        for t in r.get("trades", []):
            if days_passed >= 30 and not t.get("review_30d_done"):
                review_type = "30d"
            elif 7 <= days_passed < 30 and not t.get("review_7d_done"):
                review_type = "7d"
            else:
                continue

            side_kr = "매수" if t.get("side") == "buy" else "매도"
            name = t.get("name", "종목")
            code = str(t.get("code", "")).zfill(6)
            price = float(t.get("price") or 0)
            reason = t.get("reason")
            timing = t.get("reason_timing")

            stock = _latest_stock_close(code, r_date_str, price_cache) if code.isdigit() else None
            stock_change = _pct(stock[1], price) if stock and price else None

            if stock_change is not None:
                moved = f"그 뒤 {name}은(는) 거래가 대비 {stock_change:+}%, 코스피는 {k_diff:+}% 움직였어요."
            else:
                moved = f"그 뒤 코스피는 {k_diff:+}% 움직였어요. (종목 가격은 불러오지 못했어요)"

            if reason:
                why = f"'{reason}'"
                if timing == "이후 회상":
                    why += "(나중에 떠올려 적은 이유)"
                question = (
                    f"{days_passed}일 전 {why}(으)로 {side_kr}한 {name}. {moved} "
                    "당시 이유는 지금도 유효한가요? 다음 매매 전에 확인해 볼 점은 무엇일까요?"
                )
            else:
                question = (
                    f"{days_passed}일 전 {side_kr}한 {name}. {moved} "
                    "그때 어떤 이유로 거래했는지 기록해 두면 다음 복기 때 비교할 수 있어요."
                )

            pending_items.append(
                PendingReviewItem(
                    trade_id=t.get("id"),
                    date=r_date_str,
                    side=t.get("side", "buy"),
                    name=name,
                    code=code,
                    qty=int(t.get("qty") or 0),
                    price=price,
                    reason=reason,
                    reason_timing=timing,
                    days_passed=days_passed,
                    review_type=review_type,
                    kospi_then=kospi_then,
                    kospi_now=latest_kospi,
                    kospi_change=k_diff,
                    stock_now=stock[1] if stock else None,
                    stock_now_date=stock[0] if stock else None,
                    stock_change_vs_price=stock_change,
                    suggested_question=question
                )
            )

    return pending_items


@router.post("/{trade_id}/done")
def complete_review(
    trade_id: str,
    review_type: Literal["7d", "30d"] = Query("7d"),
    current_user: dict = Depends(get_current_user)
):
    """
    7일 또는 30일 복기 완료 처리. 30일 복기를 마치면 7일 복기도 함께 완료로 표시합니다.
    """
    for r in DataService.get_all_records():
        for t in r.get("trades", []):
            if t.get("id") == trade_id:
                update = {"review_7d_done": True}
                if review_type == "30d":
                    update["review_30d_done"] = True
                DataService.update_trade(r["date"], trade_id, TradeUpdate(**update))
                return {"message": f"{review_type} 복기를 완료로 표시했어요."}

    raise HTTPException(status_code=404, detail=f"매매 ID {trade_id}를 찾을 수 없습니다.")
