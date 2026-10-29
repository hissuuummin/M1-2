import base64
import json
import logging
import uuid
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from app.core.config import settings
from app.core.timeutil import fmt_date, parse_date, today_kst
from app.services.market_service import MarketService

logger = logging.getLogger("investment_mirror.vision_service")

MAX_IMAGE_BYTES = 5 * 1024 * 1024

PROMPT = (
    "증권사(키움 영웅문, 신한 등) 주식 체결 내역 캡처입니다. 화면에 실제로 보이는 체결 건만 "
    "JSON 배열로만 응답하세요. 보이지 않는 값은 추측하지 말고 null로 두세요.\n"
    '[{"side": "buy" 또는 "sell", "name": "종목명", "code": "6자리 코드 또는 null", '
    '"qty": 체결수량(정수), "price": 체결단가(숫자), "date": "YYYY-MM-DD 또는 null", '
    '"broker": "증권사 또는 null"}]\n'
    "체결 내역이 없으면 []만 응답하세요."
)


def _mime_type(image_bytes: bytes) -> str:
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _normalize_broker(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if "키움" in value or "영웅문" in value:
        return "키움"
    if "신한" in value:
        return "신한"
    return None


def normalize_candidates(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    AI가 읽은 값을 검증합니다. 수량·단가·매매구분·종목명이 없으면 버리고,
    코드·날짜처럼 확인이 필요한 값은 needs_check에 표시합니다. 값을 대신 채워 넣지 않습니다.
    """
    today = today_kst()
    out = []
    for t in raw if isinstance(raw, list) else []:
        if not isinstance(t, dict):
            continue
        side = t.get("side")
        name = (t.get("name") or "").strip()
        try:
            qty = int(float(str(t.get("qty")).replace(",", "")))
            price = float(str(t.get("price")).replace(",", ""))
        except (TypeError, ValueError):
            continue
        if side not in ("buy", "sell") or not name or qty <= 0 or price <= 0:
            continue

        needs_check = []
        code = str(t.get("code") or "").strip()
        if not (code.isdigit() and len(code) == 6):
            code = MarketService.get_stock_code(name) or ""
            if not code:
                needs_check.append("code")

        date_val = t.get("date")
        try:
            d = parse_date(date_val) if date_val else None
            if d and d > today:
                d = None
        except (TypeError, ValueError):
            d = None
        if d is None:
            d = today
            needs_check.append("date")

        out.append({
            "id": f"tr_{uuid.uuid4().hex[:8]}",
            "date": fmt_date(d),
            "side": side,
            "name": name,
            "code": code,
            "qty": qty,
            "price": price,
            "broker": _normalize_broker(t.get("broker")),
            "reason": None,
            "source": "capture",
            "needs_check": needs_check,
        })
    return out


class VisionService:
    @classmethod
    async def parse_trade_screenshot(cls, image_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
        """
        체결 내역 캡처를 GPT 이미지 분석으로 읽어 매매 후보를 돌려줍니다.
        이미지는 메모리에서만 처리하고 저장하지 않습니다. 인식에 실패하면 실패했다고 알립니다.
        """
        if not settings.openai_enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="캡처 인식은 OpenAI API 키가 설정되어 있어야 쓸 수 있어요."
            )
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="이미지는 5MB 이하만 올릴 수 있어요.")

        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            b64_img = base64.b64encode(image_bytes).decode("utf-8")
            res = client.chat.completions.create(
                model=settings.OPENAI_MODEL or "gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:{_mime_type(image_bytes)};base64,{b64_img}"}}
                    ]
                }],
                max_tokens=800,
                temperature=0.0
            )
            text = res.choices[0].message.content or "[]"
        except Exception as e:
            logger.warning("Vision request failed: %s", type(e).__name__)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="캡처를 분석하지 못했어요. 잠시 후 다시 시도해 주세요."
            )

        start, end = text.find("["), text.rfind("]") + 1
        try:
            raw = json.loads(text[start:end]) if start != -1 and end > start else []
        except json.JSONDecodeError:
            raw = []

        candidates = normalize_candidates(raw)
        if not candidates:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="캡처에서 체결 내역(종목·수량·단가)을 찾지 못했어요. 체결 내역 화면을 다시 캡처해 주세요."
            )
        return candidates
