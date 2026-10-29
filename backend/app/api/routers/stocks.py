from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.auth import get_current_user
from app.models.schemas import StockPricesResponse
from app.services.market_service import MarketDataError, MarketService

router = APIRouter(prefix="/stocks", tags=["Stocks"])


@router.get("/{code}/prices", response_model=StockPricesResponse)
def get_stock_and_kospi_prices(
    code: str,
    start: Optional[str] = Query(None, description="시작일 (YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="종료일 (YYYY-MM-DD)"),
    current_user: dict = Depends(get_current_user)
):
    """
    투자거울 그래프용 데이터: 선택한 종목과 코스피 지수를 기간 첫 거래일 기준 100으로 정규화한 비교 시계열 데이터 및 해당 종목 매매 내역을 반환합니다.
    """
    try:
        return MarketService.get_stock_and_kospi_comparison(
            code=code,
            start_date=start,
            end_date=end
        )
    except MarketDataError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError:
        raise HTTPException(status_code=422, detail="날짜는 YYYY-MM-DD 형식이어야 해요.")
