from typing import Any, Dict, List
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from app.core.auth import get_current_user
from app.services.importer_service import ImporterService
from app.services.vision_service import VisionService

router = APIRouter(prefix="/trades", tags=["Trades"])


@router.post("/parse-image", response_model=List[Dict[str, Any]])
async def parse_trade_screenshot(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    증권사 체결 내역 캡처 이미지로부터 매매 후보 정보를 추출합니다. (보안을 위해 이미지는 서버에 영구 저장하지 않음)
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미지 파일만 업로드할 수 있습니다."
        )

    content = await file.read()
    return await VisionService.parse_trade_screenshot(content, file.filename or "screenshot.png")


@router.post("/import-file", response_model=List[Dict[str, Any]])
async def import_trades_from_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    영웅문·신한 등 증권사에서 다운로드한 거래내역 파일(CSV 또는 엑셀)을 업로드하여 매매 후보 목록을 파싱합니다.
    이미 DB에 등록된 매매는 is_already_saved=true로 표시하여 중복 저장을 방지합니다.
    """
    filename = (file.filename or "").lower()
    if not (filename.endswith(".csv") or filename.endswith(".xlsx") or filename.endswith(".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV 또는 Excel(.xlsx, .xls) 파일만 업로드 가능합니다."
        )

    content = await file.read()
    return ImporterService.import_trades_file(content, filename)
