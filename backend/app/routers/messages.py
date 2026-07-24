"""
Message routes — rating update.

Endpoints
---------
  PATCH  /messages/{id}/rating   Update message rating (up/down) + optional feedback
"""

import uuid

from fastapi import APIRouter, HTTPException, Depends
from app.auth.dependencies import require_admin, get_current_user
from app.models.user import User
from tortoise.exceptions import DoesNotExist

from app.models.conversation import Message
from app.schemas.conversation import RatingUpdate

from app.models.agency import Agency
from app.utils import clean_agency_ids

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.patch("/{message_id}/rating", summary="Rate a message (up/down)")
async def update_rating(message_id: uuid.UUID, body: RatingUpdate) -> dict:
    try:
        msg = await Message.get(id=message_id)
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Message not found")

    msg.rating = body.rating
    if body.feedback_text is not None:
        msg.feedback_text = body.feedback_text

    update_fields = ["rating"]
    if body.feedback_text is not None:
        update_fields.append("feedback_text")

    # Update agency metrics if applicable
    if msg.rating in ("up", "down") and msg.agency_ids:
        for agency_id in clean_agency_ids(msg.agency_ids):
            try:
                agency = await Agency.get(id=agency_id)
                if msg.rating == "up":
                    agency.rating_up += 1
                elif msg.rating == "down":
                    agency.rating_down += 1
                await agency.save(update_fields=["rating_up", "rating_down"])
            except DoesNotExist:
                continue  # If agency not found, skip updating its metrics

    await msg.save(update_fields=update_fields)
    return {"success": True, "messageId": str(message_id)}
