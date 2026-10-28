from datetime import datetime, timezone
from typing import List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.auth import get_current_user
from app.models.schemas import PendingReviewItem
from app.services.data_service import DataService

router = APIRouter(prefix="/review", tags=["Review"])


@router.get("/pending", response_model=List[PendingReviewItem])
def get_pending_reviews(current_user: dict = Depends(get_current_user)):
    """
    7일·30일이 지난 미완료 매매를 조회하고, 매매 전후 시장 흐름 및 복기 질문을 생성하여 반환합니다.
    """
    records = DataService.get_all_records()
    if not records:
        return []

    sorted_records = sorted(records, key=lambda x: x["date"])
    latest_date_str = sorted_records[-1]["date"]
    latest_kospi = float(sorted_records[-1]["value"])
    latest_dt = datetime.strptime(latest_date_str, "%Y-%m-%d").date()

    pending_items: List[PendingReviewItem] = []

    for r in sorted_records:
        r_date_str = r["date"]
        r_dt = datetime.strptime(r_date_str, "%Y-%m-%d").date()
        days_passed = (latest_dt - r_dt).days
        kospi_then = float(r["value"])

        if kospi_then > 0:
            k_diff = round(((latest_kospi - kospi_then) / kospi_then) * 100, 2)
        else:
            k_diff = 0.0

        for t in r.get("trades", []):
            trade_id = t.get("id")
            side = t.get("side", "buy")
            side_kr = "매수" if side == "buy" else "매도"
            name = t.get("name", "종목")
            code = t.get("code", "005930")
            qty = int(t.get("qty", 1))
            price = float(t.get("price", 50000))
            reason = t.get("reason") or "판단 기준 미기재"
            timing = t.get("reason_timing", "당시 기록")

            # Check 7-day review
            if days_passed >= 7 and not t.get("review_7d_done"):
                question = (
                    f"{days_passed}일 전 '{reason}' 이유로 {side_kr}한 {name}. "
                    f"그 사이 코스피 지수는 {k_diff:+}% 움직였어요. "
                    f"당시 세웠던 가설과 현재 시장 흐름은 잘 맞아떨어지고 있나요?"
                )
                pending_items.append(
                    PendingReviewItem(
                        trade_id=trade_id,
                        date=r_date_str,
                        side=side,
                        name=name,
                        code=code,
                        qty=qty,
                        price=price,
                        reason=reason,
                        days_passed=days_passed,
                        review_type="7d",
                        kospi_then=kospi_then,
                        kospi_now=latest_kospi,
                        kospi_change=k_diff,
                        suggested_question=question
                    )
                )

            # Check 30-day review
            elif days_passed >= 30 and not t.get("review_30d_done"):
                question = (
                    f"한 달({days_passed}일) 전 {side_kr}했던 {name}(이유: {reason}, {timing}). "
                    f"한 달간 코스피는 {k_diff:+}% 변화했습니다. "
                    "단기 등락을 떠나 이 거래가 내 투자 원칙에 부합했는지 돌아볼 좋은 시점입니다."
                )
                pending_items.append(
                    PendingReviewItem(
                        trade_id=trade_id,
                        date=r_date_str,
                        side=side,
                        name=name,
                        code=code,
                        qty=qty,
                        price=price,
                        reason=reason,
                        days_passed=days_passed,
                        review_type="30d",
                        kospi_then=kospi_then,
                        kospi_now=latest_kospi,
                        kospi_change=k_diff,
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
    7일 또는 30일 복기 완료 처리
    """
    records = DataService.get_all_records()
    found = False

    for r in records:
        date_id = r["date"]
        for t in r.get("trades", []):
            if t.get("id") == trade_id:
                field = "review_7d_done" if review_type == "7d" else "review_30d_done"
                DataService.update_trade(date_id, trade_id, **{field: True})
                found = True
                break
        if found:
            break

    if not found:
        raise HTTPException(status_code=404, detail=f"매매 ID {trade_id}를 찾을 수 없습니다.")

    return {"message": f"매매 ID {trade_id}의 {review_type} 복기가 완료 처리되었습니다."}
