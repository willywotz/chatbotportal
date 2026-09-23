"""Public, unauthenticated agency status — name, status, 24h uptime. No internals."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.features.analytics.services import public_status as public_status_service

router = APIRouter(prefix="/public", tags=["Public"])


async def public_status(session: AsyncSession) -> list[dict]:
    return await public_status_service.public_status(session)


@router.get("/status", summary="Public agency status")
async def get_public_status(session: AsyncSession = Depends(get_db)) -> list[dict]:
    return await public_status(session)


async def public_agencies(session: AsyncSession) -> list[dict]:
    """Display-safe agency list for the public portal — no internals."""
    return await public_status_service.public_agencies(session)


@router.get("/agencies", summary="Public agency directory")
async def get_public_agencies(session: AsyncSession = Depends(get_db)) -> list[dict]:
    return await public_agencies(session)
