"""
Message routes — rating update.

Endpoints
---------
  PATCH  /messages/{id}/rating   Update message rating (up/down) + optional feedback
"""

import uuid

from fastapi import APIRouter

from app.schemas.conversation import RatingUpdate
from app.services import message as message_service

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.patch("/{message_id}/rating", summary="Rate a message (up/down)")
async def update_rating(message_id: uuid.UUID, body: RatingUpdate) -> dict:
    msg = await message_service.update_rating(message_id, body)
    return {"success": True, "messageId": str(msg.id)}
