"""
Conversation & message-history routes.

Endpoints
---------
  POST   /history                Save a new conversation (with messages)
  GET    /history                List conversations (history) — with search/filter
  GET    /history/{id}           Get single conversation with messages
  DELETE /history/{id}           Delete conversation (cascades to messages)
"""

import time
import uuid

from fastapi import APIRouter, Depends, Query, status

from app.auth.dependencies import get_current_user, get_current_user_optional
from app.models.user import User
from app.schemas.conversation import HistoryItem, HistoryResponse, SaveConversationRequest
from app.services import conversation as conversation_service

router = APIRouter(prefix="/history", tags=["History"])


# ---------------------------------------------------------------------------
# Save conversation  (mirrors save-conversation edge function)
# ---------------------------------------------------------------------------

@router.post(
    "",
    summary="Save conversation with messages",
    status_code=status.HTTP_201_CREATED,
)
async def save_conversation(body: SaveConversationRequest, user: User | None = Depends(get_current_user_optional)) -> dict:
    conv = await conversation_service.create_conversation(body, user)
    return {"success": True, "conversationId": str(conv.id)}


# ---------------------------------------------------------------------------
# List / history  (mirrors chat-history edge function)
# ---------------------------------------------------------------------------

@router.get("", summary="List conversations (history)")
async def list_conversations(
    search: str = Query("", description="Search in title or preview"),
    filter_agency: str = Query("", alias="filterAgency", description="Filter by agency name"),
    date_from: str | None = Query(None, description="Inclusive start date YYYY-MM-DD"),
    date_to: str | None = Query(None, description="Inclusive end date YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int | None = Query(None, ge=1, le=200, description="Omit for full list (legacy)"),
    user: User = Depends(get_current_user),
) -> HistoryResponse:
    start = time.time()

    convs, total = await conversation_service.list_conversations(
        user=user,
        search=search,
        filter_agency=filter_agency,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )

    items = [
        HistoryItem(
            id=str(c.id),
            title=c.title,
            preview=c.preview or "",
            date=c.created_at.strftime("%Y-%m-%d"),
            agencies=[],
            status=c.status,
            message_count=c.message_count or 0,
            response_time=c.response_time or "",
        )
        for c in convs
    ]

    return HistoryResponse(
        success=True,
        data=items,
        total=total,
        response_time=int((time.time() - start) * 1000),
    )


# ---------------------------------------------------------------------------
# Get single conversation with messages
# ---------------------------------------------------------------------------

@router.get("/{conversation_id}", summary="Get conversation with messages")
async def get_conversation(conversation_id: uuid.UUID, user: User = Depends(get_current_user)) -> dict:
    conv, messages = await conversation_service.get_conversation_with_messages(conversation_id, user)
    return {
        "id": str(conv.id),
        "title": conv.title,
        "preview": conv.preview,
        "agencies": conv.agencies,
        "status": conv.status,
        "message_count": conv.message_count,
        "response_time": conv.response_time,
        "created_at": conv.created_at.isoformat(),
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "agent_steps": m.agent_steps,
                "sources": m.sources,
                "summary": m.summary,
                "summary_references": m.summary_references or [],
                "rating": m.rating,
                "feedback_text": m.feedback_text,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }

@router.get("/{conversation_id}/messages", summary="Get messages for a conversation")
async def get_conversation_messages(conversation_id: uuid.UUID, user: User = Depends(get_current_user)) -> list[dict]:
    messages = await conversation_service.get_conversation_messages(conversation_id, user)
    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "agent_steps": m.agent_steps,
            "sources": m.sources,
            "summary": m.summary,
            "summary_references": m.summary_references or [],
            "rating": m.rating,
            "feedback_text": m.feedback_text,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


# ---------------------------------------------------------------------------
# Delete conversation (cascade to messages via DB FK)
# ---------------------------------------------------------------------------

@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete conversation")
async def delete_conversation(conversation_id: uuid.UUID, user: User = Depends(get_current_user)) -> None:
    await conversation_service.delete_conversation(conversation_id, user)
