from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from tortoise.exceptions import DoesNotExist

from app.models.agency import Agency
from app.models.conversation import Message
from app.schemas.conversation import RatingUpdate
from app.utils import clean_agency_ids


async def update_rating(message_id: uuid.UUID, body: RatingUpdate) -> Message:
    """Persist a message rating and roll it into each listed agency's metrics."""
    try:
        msg = await Message.get(id=message_id)
    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    msg.rating = body.rating
    if body.feedback_text is not None:
        msg.feedback_text = body.feedback_text

    update_fields = ["rating"]
    if body.feedback_text is not None:
        update_fields.append("feedback_text")

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
                continue

    await msg.save(update_fields=update_fields)
    return msg
