from typing import List
from fastapi import APIRouter, Depends, status
from app.core.auth import get_current_user
from app.models.schemas import (
    ConversationCreate,
    ConversationListItem,
    ConversationResponse,
)
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    req: ConversationCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    새로운 대화 세션 저장
    """
    messages_data = [m.model_dump() for m in req.messages]
    return ConversationService.create_conversation(title=req.title, messages=messages_data)


@router.get("", response_model=List[ConversationListItem])
def list_conversations(current_user: dict = Depends(get_current_user)):
    """
    대화 목록 조회 (대화 목록 UX: id, 제목, 날짜, 메시지 수 반환, messages 본문 제외)
    """
    return ConversationService.list_conversations()


@router.get("/{conv_id}", response_model=ConversationResponse)
def get_conversation_detail(
    conv_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    특정 대화의 전체 messages 본문 불러오기 (대화 복원 UX)
    """
    return ConversationService.get_conversation(conv_id)


@router.delete("/{conv_id}")
def delete_conversation(
    conv_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    특정 대화 삭제
    """
    ConversationService.delete_conversation(conv_id)
    return {"message": f"대화 ID {conv_id}가 삭제되었습니다."}
