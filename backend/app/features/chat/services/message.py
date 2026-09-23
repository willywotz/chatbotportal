from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, ErrorCode
from app.features.chat.models.conversation import Message
from app.features.agency.repositories import agency as agency_repo
from app.features.chat.repositories import message as message_repo
from app.features.chat.schemas.conversation import RatingUpdate
from app.core.utils import clean_agency_ids


async def update_rating(session: AsyncSession, message_id: uuid.UUID, body: RatingUpdate) -> Message:
    """Persist a message rating and roll it into each listed agency's metrics."""
    msg = await message_repo.by_id(session, message_id)
    if msg is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Message not found", status=404)

    msg.rating = body.rating
    if body.feedback_text is not None:
        msg.feedback_text = body.feedback_text

    update_fields = ["rating"]
    if body.feedback_text is not None:
        update_fields.append("feedback_text")

    if msg.rating in ("up", "down") and msg.agency_ids:
        for agency_id in clean_agency_ids(msg.agency_ids):
            agency = await agency_repo.by_id(session, agency_id)
            if agency is None:
                continue
            if msg.rating == "up":
                agency.rating_up += 1
            elif msg.rating == "down":
                agency.rating_down += 1
            await agency_repo.save(session, agency, update_fields=["rating_up", "rating_down"])

    await message_repo.save(session, msg, update_fields=update_fields)
    return msg
