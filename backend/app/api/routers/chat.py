from fastapi import APIRouter, Depends
from app.core.auth import get_current_user
from app.models.schemas import ChatRequest, ChatResponse
from app.services.ai_service import AIService

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
async def chat_with_assistant(
    req: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    AI 챗봇 대화 API (컨텍스트 주입 + 도구 호출 + 대화 자동 저장)
    - 데이터 요약(코스피/매매 지표)을 시스템 프롬프트에 자동 주입
    - 필요 시 GPT가 record_trade, get_stock_change 등의 도구를 자율적으로 호출
    - 대화 완료 후 conversations 컬렉션에 자동 저장
    """
    return await AIService.process_chat(
        user_message=req.message,
        conversation_id=req.conversation_id
    )
