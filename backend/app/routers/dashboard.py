import time

from fastapi import APIRouter, Depends, Security
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_scope
from app.auth.principal import Principal
from app.db import get_db
from app.services.analytics import get_dashboard_stats

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/statistics", summary="Get dashboard statistics and charts data")
async def dashboard_stats(
    session: AsyncSession = Depends(get_db),
    _user: Principal = Security(require_scope, scopes=["dashboard:read"]),
) -> dict:
    start = time.time()
    data = await get_dashboard_stats(session)
    return {"success": True, "data": data, "responseTime": int((time.time() - start) * 1000)}
