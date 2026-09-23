from fastapi import APIRouter, Depends, Security
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.dependencies import require_scope
from app.core.security.principal import Principal
from app.core.db import get_db
from app.features.analytics.schemas.executive_summary import ExecutiveData
from app.features.analytics.services import get_executive_summary, regenerate_weekly_brief

router = APIRouter(tags=["executive"])


@router.get("/executive-summary", operation_id="get_executive_summary")
async def executive_summary_endpoint(
    session: AsyncSession = Depends(get_db),
    _: Principal = Security(require_scope, scopes=["executive:read"]),
) -> ExecutiveData:
    return await get_executive_summary(session)


@router.post("/executive-summary/regenerate", operation_id="regenerate_executive_summary")
async def regenerate_executive_summary_endpoint(
    session: AsyncSession = Depends(get_db),
    _: Principal = Security(require_scope, scopes=["executive:write"]),
) -> dict:
    brief = await regenerate_weekly_brief(session)
    return {"weeklyBrief": brief.content, "status": brief.status, "generatedAt": brief.generated_at}
