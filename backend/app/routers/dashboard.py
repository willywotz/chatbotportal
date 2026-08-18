import time

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.models.user import User
from app.services.analytics import get_dashboard_stats

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# Authorization is enforced by the global role allowlist (enforce_role_allowlist):
# admin passes the allowlist; a plain `user` is blocked upstream.
@router.get("/statistics", summary="Get dashboard statistics and charts data")
async def dashboard_stats(_user: User = Depends(get_current_user)) -> dict:
    start = time.time()
    data = await get_dashboard_stats()
    return {"success": True, "data": data, "responseTime": int((time.time() - start) * 1000)}
