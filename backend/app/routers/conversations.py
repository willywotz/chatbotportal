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
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status, Depends
from app.auth.dependencies import get_current_user, get_current_user_optional
from app.models.user import User
from tortoise.exceptions import DoesNotExist

from app.models.conversation import Conversation, Message
from app.schemas.conversation import (
    ConversationResponse,
    HistoryItem,
    HistoryResponse,
    SaveConversationRequest,
)
from app.utils import now

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
    # Create conversation record
    conv = await Conversation.create(
        title=body.title or "สนทนาใหม่",
        preview=body.preview or "",
        agencies=body.agencies,
        status=body.status,
        message_count=len(body.messages),
        response_time=body.response_time,
        user_id=user.id if user else None,
    )

    # Bulk-insert messages
    if body.messages:
        msg_rows = []
        for m in body.messages:
            msg_rows.append(
                Message(
                    id=m.id or uuid.uuid4(),
                    conversation_id=conv.id,
                    role=m.role,
                    content=m.content,
                    agent_steps=m.agent_steps or [],
                    sources=m.sources or [],
                    rating=m.rating,
                    feedback_text=m.feedback_text,
                    user_id=user.id if user else None,
                )
            )
        await Message.bulk_create(msg_rows, ignore_conflicts=True)

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

    qs = Conversation.all()

    if not user.is_admin:
        qs = qs.filter(user_id=user.id)

    if search:
        qs = qs.filter(title__icontains=search)

    if filter_agency:
        qs = qs.filter(agencies__contains=filter_agency)

    if date_from:
        try:
            qs = qs.filter(created_at__gte=datetime.strptime(date_from, "%Y-%m-%d"))
        except ValueError:
            raise HTTPException(status_code=400, detail="date_from must be YYYY-MM-DD")

    if date_to:
        try:
            end = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            qs = qs.filter(created_at__lt=end)
        except ValueError:
            raise HTTPException(status_code=400, detail="date_to must be YYYY-MM-DD")

    total = await qs.count()

    page_qs = qs.order_by("-created_at")
    if page_size is not None:
        page_qs = page_qs.offset((page - 1) * page_size).limit(page_size)
    convs = await page_qs

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
    try:
        conv = await Conversation.get(id=conversation_id)
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if str(conv.user_id) != str(user.id) and not user.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")

    messages = await Message.filter(conversation_id=conversation_id).order_by("created_at")

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
    try:
        conv = await Conversation.get(id=conversation_id)
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if str(conv.user_id) != str(user.id) and not user.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")

    messages = await Message.filter(conversation_id=conversation_id).order_by("created_at")

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
    try:
        conv = await Conversation.get(id=conversation_id)
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if str(conv.user_id) != str(user.id) and not user.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")
    await conv.delete()
