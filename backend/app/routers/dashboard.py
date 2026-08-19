import time

from fastapi import APIRouter, Security

from app.auth.dependencies import require_scope
from app.auth.keycloak import Principal
from app.services.analytics import get_dashboard_stats

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/statistics", summary="Get dashboard statistics and charts data")
async def dashboard_stats(_user: Principal = Security(require_scope, scopes=["dashboard:read"])) -> dict:
    start = time.time()
    data = await get_dashboard_stats()
    return {"success": True, "data": data, "responseTime": int((time.time() - start) * 1000)}
