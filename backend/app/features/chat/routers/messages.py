import uuid

from fastapi import APIRouter, Depends, Security
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.dependencies import require_scope
from app.core.security.principal import Principal
from app.core.db import get_db
from app.features.chat.schemas.conversation import RatingUpdate
from app.features.chat.services import message as message_service

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.patch("/{message_id}/rating", summary="Rate a message (up/down)")
async def update_rating(
    message_id: uuid.UUID,
    body: RatingUpdate,
    session: AsyncSession = Depends(get_db),
    _: Principal = Security(require_scope, scopes=["message:rate"]),
) -> dict:
    msg = await message_service.update_rating(session, message_id, body)
    return {"success": True, "messageId": str(msg.id)}
