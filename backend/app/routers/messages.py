import uuid

from fastapi import APIRouter, Depends, Security
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_scope
from app.auth.principal import Principal
from app.db import get_db
from app.schemas.conversation import RatingUpdate
from app.services import message as message_service

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
