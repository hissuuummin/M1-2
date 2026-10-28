from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid
from fastapi import HTTPException, status
from app.core.firebase import get_firestore_client
from app.models.schemas import (
    ChatMessage,
    ConversationListItem,
    ConversationResponse,
)

logger = logging.getLogger("investment_mirror.conversation_service")


class ConversationService:
    @staticmethod
    def _get_collection():
        db = get_firestore_client()
        return db.collection("conversations")

    @classmethod
    def list_conversations(cls) -> List[ConversationListItem]:
        col = cls._get_collection()
        docs = col.stream()

        items = []
        for d in docs:
            data = d.to_dict()
            if not data:
                continue
            conv_id = d.id
            title = data.get("title") or "새로운 대화"
            created_at = data.get("created_at") or datetime.now(timezone.utc).isoformat()
            updated_at = data.get("updated_at")
            messages = data.get("messages", [])
            items.append(
                ConversationListItem(
                    id=conv_id,
                    title=title,
                    created_at=created_at,
                    updated_at=updated_at,
                    message_count=len(messages)
                )
            )

        items.sort(key=lambda x: x.created_at, reverse=True)
        return items

    @classmethod
    def get_conversation(cls, conv_id: str) -> ConversationResponse:
        col = cls._get_collection()
        doc = col.document(conv_id).get()

        if not doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"대화 ID {conv_id}를 찾을 수 없습니다."
            )

        data = doc.to_dict()
        msgs = [ChatMessage(**m) for m in data.get("messages", [])]
        return ConversationResponse(
            id=doc.id,
            title=data.get("title", "대화"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at"),
            messages=msgs
        )

    @classmethod
    def create_conversation(
        cls,
        title: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None
    ) -> ConversationResponse:
        col = cls._get_collection()
        conv_id = uuid.uuid4().hex[:12]
        now_iso = datetime.now(timezone.utc).isoformat()

        if not title:
            if messages and len(messages) > 0:
                first_content = messages[0].get("content", "")
                title = first_content[:30] + ("..." if len(first_content) > 30 else "")
            else:
                title = "새 대화"

        msgs = messages or []
        doc_data = {
            "title": title,
            "created_at": now_iso,
            "updated_at": now_iso,
            "messages": msgs
        }
        col.document(conv_id).set(doc_data)
        return ConversationResponse(
            id=conv_id,
            title=title,
            created_at=now_iso,
            updated_at=now_iso,
            messages=[ChatMessage(**m) for m in msgs]
        )

    @classmethod
    def append_messages(
        cls,
        conv_id: Optional[str],
        user_message: str,
        assistant_reply: str,
        sources: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        col = cls._get_collection()
        now_iso = datetime.now(timezone.utc).isoformat()

        user_msg = {
            "role": "user",
            "content": user_message,
            "sources": [],
            "created_at": now_iso
        }
        ai_msg = {
            "role": "assistant",
            "content": assistant_reply,
            "sources": sources or [],
            "created_at": now_iso
        }

        if not conv_id:
            # Auto-create new conversation
            conv_id = uuid.uuid4().hex[:12]
            title = user_message[:25] + ("..." if len(user_message) > 25 else "")
            doc_data = {
                "title": title,
                "created_at": now_iso,
                "updated_at": now_iso,
                "messages": [user_msg, ai_msg]
            }
            col.document(conv_id).set(doc_data)
            return conv_id

        doc_ref = col.document(conv_id)
        doc = doc_ref.get()

        if not doc.exists:
            title = user_message[:25] + ("..." if len(user_message) > 25 else "")
            doc_data = {
                "title": title,
                "created_at": now_iso,
                "updated_at": now_iso,
                "messages": [user_msg, ai_msg]
            }
            doc_ref.set(doc_data)
            return conv_id

        data = doc.to_dict()
        msgs = data.get("messages", [])
        msgs.append(user_msg)
        msgs.append(ai_msg)
        data["messages"] = msgs
        data["updated_at"] = now_iso
        doc_ref.set(data)
        return conv_id

    @classmethod
    def delete_conversation(cls, conv_id: str) -> bool:
        col = cls._get_collection()
        doc_ref = col.document(conv_id)
        doc = doc_ref.get()

        if not doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"대화 ID {conv_id}를 찾을 수 없습니다."
            )

        doc_ref.delete()
        return True
