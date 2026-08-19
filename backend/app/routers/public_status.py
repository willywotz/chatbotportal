"""Public, unauthenticated agency status — name, status, 24h uptime. No internals."""
from fastapi import APIRouter

from app.routers.agencies.logo import get_agency_logo
from app.services import public_status as public_status_service

router = APIRouter(prefix="/public", tags=["Public"])
router.get("/agencies/{agency_id}/logo", summary="Get agency logo image")(get_agency_logo)


async def public_status() -> list[dict]:
    return await public_status_service.public_status()


@router.get("/status", summary="Public agency status")
async def get_public_status() -> list[dict]:
    return await public_status()


async def public_agencies() -> list[dict]:
    """Display-safe agency list for the public portal — no internals."""
    return await public_status_service.public_agencies()


@router.get("/agencies", summary="Public agency directory")
async def get_public_agencies() -> list[dict]:
    return await public_agencies()
