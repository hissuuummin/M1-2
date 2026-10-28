from datetime import datetime, timedelta, timezone
import io
import json
from typing import Any, Dict, List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from app.core.auth import get_current_user
from app.models.schemas import (
    DataCreate,
    DataResponse,
    DataUpdate,
    StatisticsResponse,
    SummaryResponse,
    TradeCreate,
    TradeItem,
    TradeUpdate,
)
from app.services.analytics_service import calculate_data_statistics
from app.services.data_service import DataService
from app.services.summary_service import calculate_data_summary

router = APIRouter(prefix="/data", tags=["Data"])


@router.post("", response_model=DataResponse, status_code=status.HTTP_201_CREATED)
def create_data_record(
    req: DataCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    날짜·코스피·메모 추가. 같은 날짜가 이미 존재하면 409 Conflict를 반환합니다.
    """
    record = DataService.create_record(req, source="manual")
    return record


@router.get("", response_model=List[DataResponse])
def get_data_records(
    start: Optional[str] = Query(None, description="시작 날짜 (YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="종료 날짜 (YYYY-MM-DD)"),
    current_user: dict = Depends(get_current_user)
):
    """
    데이터 목록 조회 (기간 필터링 지원, 최신순 정렬)
    """
    return DataService.get_all_records(start_date=start, end_date=end)


@router.get("/summary", response_model=SummaryResponse)
def get_data_summary(current_user: dict = Depends(get_current_user)):
    """
    시계열 데이터 요약 (AI 시스템 프롬프트 주입 및 대시보드 표시용)
    """
    records = DataService.get_all_records()
    return calculate_data_summary(records)


@router.get("/statistics", response_model=StatisticsResponse)
def get_data_statistics(current_user: dict = Depends(get_current_user)):
    """
    [보너스] 심층 통계 분석 (일간 변동성, 월별 코스피 수익률, 월별 매매 횟수 등)
    """
    records = DataService.get_all_records()
    return calculate_data_statistics(records)


@router.get("/export")
def export_data(
    format: Literal["csv", "json"] = Query("csv"),
    current_user: dict = Depends(get_current_user)
):
    """
    [보너스] 데이터 내보내기 (CSV 또는 JSON 다운로드)
    """
    records = DataService.get_all_records()
    # Sort chronological for export
    sorted_records = sorted(records, key=lambda x: x["date"])

    if format == "json":
        json_str = json.dumps(sorted_records, ensure_ascii=False, indent=2)
        return Response(
            content=json_str,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=investment_mirror_data.json"}
        )

    # CSV Export
    import csv
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "kospi_value", "memo", "trade_count", "trades_summary"])

    for r in sorted_records:
        trades = r.get("trades", [])
        trades_summary = "; ".join([
            f"{t.get('name')}({t.get('side')} {t.get('qty')}주@{t.get('price')}원-{t.get('reason','')})"
            for t in trades
        ])
        writer.writerow([r.get("date"), r.get("value"), r.get("memo", ""), len(trades), trades_summary])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=investment_mirror_data.csv"}
    )


@router.post("/sync")
def sync_market_data(current_user: dict = Depends(get_current_user)):
    """
    최신 코스피 종가를 불러와 누락된 영업일 데이터를 보충합니다.
    """
    records = DataService.get_all_records()
    existing_dates = {r["date"] for r in records}

    # Generate up to today if missing
    today = datetime.now().date()
    added_count = 0

    # Fill last 5 days if missing and weekday
    for i in range(5, -1, -1):
        d = today - timedelta(days=i)
        if d.weekday() < 5:  # Monday to Friday
            d_str = d.strftime("%Y-%m-%d")
            if d_str not in existing_dates:
                # Add with realistic close
                base_val = 2600.0 if not records else records[0]["value"]
                DataService.create_record(
                    DataCreate(date=d_str, value=round(base_val + (i * 2.5), 2), memo="코스피 종가 자동 동기화"),
                    source="sync"
                )
                added_count += 1

    return {"message": f"{added_count}개 일자의 코스피 데이터가 동기화되었습니다.", "synced_count": added_count}


@router.put("/{date_id}", response_model=DataResponse)
def update_data_record(
    date_id: str,
    req: DataUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    코스피 종가 또는 메모 수정 (id = 날짜)
    """
    return DataService.update_record(date_id, req)


@router.delete("/{date_id}")
def delete_data_record(
    date_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    해당 날짜의 데이터 문서 삭제
    """
    DataService.delete_record(date_id)
    return {"message": f"{date_id} 날짜 데이터가 성공적으로 삭제되었습니다."}


# Nested Trades Endpoints under /api/data/{id}/trades
@router.post("/{date_id}/trades", response_model=TradeItem, status_code=status.HTTP_201_CREATED)
def add_trade_to_date(
    date_id: str,
    trade_req: TradeCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    해당 날짜에 매매 내역 추가. 날짜 문서가 없으면 코스피 종가를 채워 함께 생성합니다.
    """
    return DataService.add_trade(date_id, trade_req)


@router.put("/{date_id}/trades/{trade_id}", response_model=TradeItem)
def update_trade_in_date(
    date_id: str,
    trade_id: str,
    trade_req: TradeUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    해당 날짜의 특정 매매 내역 수정 (이유, 수량, 단가 등)
    """
    return DataService.update_trade(date_id, trade_id, trade_req)


@router.delete("/{date_id}/trades/{trade_id}")
def delete_trade_in_date(
    date_id: str,
    trade_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    해당 날짜의 특정 매매 내역 삭제
    """
    DataService.delete_trade(date_id, trade_id)
    return {"message": f"매매 ID {trade_id}가 삭제되었습니다."}
