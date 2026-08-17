"""
Seed router — manually populate default data.

Endpoints
---------
  POST  /seed/admin      Create default admin (admin@example.com / admin1234)
  POST  /seed/agencies   Create the 4 default government agencies
  POST  /seed/all        Run both seeders above in one call
"""

from fastapi import APIRouter, Depends

from app.auth.dependencies import require_admin
from app.models.user import User
from app.services import seed as seed_service

router = APIRouter(prefix="/seed", tags=["Seed"])


@router.post("/admin", summary="Seed default admin account")
async def seed_admin(_: User = Depends(require_admin)) -> dict:
    return await seed_service.run_seed_admin()


@router.post("/agencies", summary="Seed default government agencies")
async def seed_agencies(_: User = Depends(require_admin)) -> dict:
    return await seed_service.run_seed_agencies()


@router.post("/all", summary="Seed all default data (admin + agencies)")
async def seed_all(_: User = Depends(require_admin)) -> dict:
    return {
        "admin": await seed_service.run_seed_admin(),
        "agencies": await seed_service.run_seed_agencies(),
    }
