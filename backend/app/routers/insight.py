from datetime import datetime

from fastapi import APIRouter, Query, Security

from app.auth.dependencies import require_scope
from app.auth.keycloak import Principal
from app.schemas.insight import AgencyHealthData, AnalyticsInsightsData, HeatmapRange, UsageHeatmapData
from app.services.analytics import get_agency_health, get_usage_heatmap, usage_summary
from app.utils import now

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
    _: Principal = Security(require_scope, scopes=["health:read"]),
) -> AgencyHealthData:
    return await get_agency_health()

@router.get("/usage-heatmap")
async def get_insight_usage_heatmap(
    range: HeatmapRange,
    _: Principal = Security(require_scope, scopes=["usage:read"]),
) -> UsageHeatmapData:
    return await get_usage_heatmap(range)


@router.get("/insight/usage", summary="LLM token/cost usage grouped")
async def get_usage(
    group_by: str = "purpose",
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    _user: Principal = Security(require_scope, scopes=["usage:read"]),
):
    return await usage_summary(group_by=group_by, date_from=date_from, date_to=date_to)
