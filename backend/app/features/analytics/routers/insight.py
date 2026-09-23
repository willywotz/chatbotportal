from datetime import datetime

from fastapi import APIRouter, Depends, Query, Security
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.dependencies import require_scope
from app.core.security.principal import Principal
from app.core.db import get_db
from app.features.analytics.schemas.insight import AgencyHealthData, AnalyticsInsightsData, HeatmapRange, UsageHeatmapData
from app.features.analytics.services import get_agency_health, get_usage_heatmap, usage_summary
from app.core.utils import now

router = APIRouter(tags=["insight"])


@router.get("/analytics-insights")
async def get_insight_analytics_insights(
    _: Principal = Security(require_scope, scopes=["analytics:read"]),
) -> AnalyticsInsightsData:
    return AnalyticsInsightsData(
        totalWeekQuestions=0,
        topicClusters=[],
        sentimentDist={"positive": 0, "neutral": 0, "negative": 0},
        noAnswerByAgency=[],
        dailyVolume=[],
        trendingTopics=[],
        decliningTopics=[],
        aiInsights="",
        recommendations=[],
        generatedAt=now()
    )

@router.get("/agency-health")
async def get_insight_agency_health(
    session: AsyncSession = Depends(get_db),
    _: Principal = Security(require_scope, scopes=["health:read"]),
) -> AgencyHealthData:
    return await get_agency_health(session)

@router.get("/usage-heatmap")
async def get_insight_usage_heatmap(
    range: HeatmapRange,
    session: AsyncSession = Depends(get_db),
    _: Principal = Security(require_scope, scopes=["usage:read"]),
) -> UsageHeatmapData:
    return await get_usage_heatmap(session, range)


@router.get("/insight/usage", summary="LLM token/cost usage grouped")
async def get_usage(
    group_by: str = "purpose",
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    session: AsyncSession = Depends(get_db),
    _user: Principal = Security(require_scope, scopes=["usage:read"]),
):
    return await usage_summary(session, group_by=group_by, date_from=date_from, date_to=date_to)
