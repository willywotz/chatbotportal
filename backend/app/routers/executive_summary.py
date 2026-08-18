from fastapi import APIRouter, Security

from app.auth.dependencies import require_scope
from app.auth.keycloak import Principal
from app.schemas.executive_summary import ExecutiveData
from app.services.analytics import get_executive_summary, regenerate_weekly_brief

router = APIRouter(tags=["executive"])


@router.get("/executive-summary", operation_id="get_executive_summary")
async def executive_summary_endpoint(
    _: Principal = Security(require_scope, scopes=["executive:read"]),
) -> ExecutiveData:
    return await get_executive_summary()


@router.post("/executive-summary/regenerate", operation_id="regenerate_executive_summary")
async def regenerate_executive_summary_endpoint(
    _: Principal = Security(require_scope, scopes=["executive:write"]),
) -> dict:
    brief = await regenerate_weekly_brief()
    return {"weeklyBrief": brief.content, "status": brief.status, "generatedAt": brief.generated_at}
