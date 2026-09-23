"""HTTP-level scope enforcement for the staff-facing ops dashboards.

A `staff` bundle (dashboard:read, executive:read, health:read, usage:read,
feedback:read) reaches the six read-only dashboards but not the
analytics-insights page, the executive-summary regenerate write, or the
feedback low-rated detail — those need scopes the staff bundle omits.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.features.chat.schemas.conversation import FeedbackStats
from app.features.analytics.schemas.executive_summary import ExecutiveData, ExecutiveKPIs
from app.features.analytics.schemas.insight import AgencyHealthData, BusiestInsight, HeatmapInsights, UsageHeatmapData
from app.core.utils import now

_STAFF_SCOPES = ["dashboard:read", "executive:read", "health:read", "usage:read", "feedback:read"]

_KPI_FIELDS = [
    "totalQuestions", "momGrowth", "yoyGrowth", "uniqueCitizens", "totalHoursSaved",
    "costSaved", "healthScore", "uptime", "satisfaction", "avgResponseTime",
    "thisMonthQuestions", "lastMonthQuestions", "thisYearQuestions", "lastYearQuestions",
    "momGrowthQuestions", "yoyGrowthQuestions", "thisMonthCitizens", "lastMonthCitizens",
    "thisYearCitizens", "lastYearCitizens", "momGrowthCitizens", "yoyGrowthCitizens",
]


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _executive_data() -> ExecutiveData:
    return ExecutiveData(
        kpis=ExecutiveKPIs(**dict.fromkeys(_KPI_FIELDS, 0)),
        agencyScorecard=[], monthlyTrend=[], topIssues=[], weeklyBrief="", generatedAt=now(),
    )


def _agency_health() -> AgencyHealthData:
    return AgencyHealthData(agencies=[], historical=[], incidents=[], slaCompliance=[], generatedAt=now())


def _usage_heatmap() -> UsageHeatmapData:
    return UsageHeatmapData(
        range="7d", days=7, sampleSize=0, totalMessages=0, days_labels=[], hours=[], agencies=[],
        hourlyByAgency=[], dayHourMatrix=[],
        insights=HeatmapInsights(
            peakDay="", peakHour="", peakValue=0, totalRequests=0, businessHoursPercent=0.0,
            busiest=BusiestInsight(agency="", total=0, peakHour=0), recommendation="",
        ),
        generatedAt=now(),
    )


def _feedback_stats() -> FeedbackStats:
    return FeedbackStats(total_ratings=0, up_count=0, down_count=0, satisfaction_rate=0,
                         daily_trend=[], low_rated_questions=[], agency_breakdown=[])


async def test_staff_reaches_dashboard_statistics(as_principal):
    as_principal(role="staff", scopes=_STAFF_SCOPES)
    from app.features.analytics.routers import dashboard as router_module
    with patch.object(router_module, "get_dashboard_stats", new=AsyncMock(return_value={})):
        async with await _client() as c:
            r = await c.get("/api/v1/dashboard/statistics")
    assert r.status_code == 200


async def test_staff_reaches_executive_summary(as_principal):
    as_principal(role="staff", scopes=_STAFF_SCOPES)
    from app.features.analytics.routers import executive_summary as router_module
    with patch.object(router_module, "get_executive_summary", new=AsyncMock(return_value=_executive_data())):
        async with await _client() as c:
            r = await c.get("/api/v1/executive-summary")
    assert r.status_code == 200


async def test_staff_reaches_agency_health(as_principal):
    as_principal(role="staff", scopes=_STAFF_SCOPES)
    from app.features.analytics.routers import insight as router_module
    with patch.object(router_module, "get_agency_health", new=AsyncMock(return_value=_agency_health())):
        async with await _client() as c:
            r = await c.get("/api/v1/agency-health")
    assert r.status_code == 200


async def test_staff_reaches_usage_heatmap(as_principal):
    as_principal(role="staff", scopes=_STAFF_SCOPES)
    from app.features.analytics.routers import insight as router_module
    with patch.object(router_module, "get_usage_heatmap", new=AsyncMock(return_value=_usage_heatmap())):
        async with await _client() as c:
            r = await c.get("/api/v1/usage-heatmap", params={"range": "7d"})
    assert r.status_code == 200


async def test_staff_reaches_insight_usage(as_principal):
    as_principal(role="staff", scopes=_STAFF_SCOPES)
    from app.features.analytics.routers import insight as router_module
    with patch.object(router_module, "usage_summary", new=AsyncMock(return_value=[])):
        async with await _client() as c:
            r = await c.get("/api/v1/insight/usage")
    assert r.status_code == 200


async def test_staff_reaches_feedback_statistics(as_principal):
    as_principal(role="staff", scopes=_STAFF_SCOPES)
    from app.features.analytics.routers import feedback as router_module
    with patch.object(router_module, "get_feedback_stats", new=AsyncMock(return_value=_feedback_stats())):
        async with await _client() as c:
            r = await c.get("/api/v1/feedback/statistics")
    assert r.status_code == 200


async def test_staff_denied_analytics_insights(as_principal):
    as_principal(role="staff", scopes=_STAFF_SCOPES)
    async with await _client() as c:
        r = await c.get("/api/v1/analytics-insights")
    assert r.status_code == 403


async def test_staff_denied_executive_summary_regenerate(as_principal):
    as_principal(role="staff", scopes=_STAFF_SCOPES)
    async with await _client() as c:
        r = await c.post("/api/v1/executive-summary/regenerate")
    assert r.status_code == 403


async def test_staff_denied_feedback_low_rated(as_principal):
    as_principal(role="staff", scopes=_STAFF_SCOPES)
    async with await _client() as c:
        r = await c.get("/api/v1/feedback/agencies/abc-123/low-rated")
    assert r.status_code == 403
