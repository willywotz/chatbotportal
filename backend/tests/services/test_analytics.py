"""Service-level tests for app.features.analytics.services.* against real Postgres (db_session)."""
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.features.agency.models.agency import Agency
from app.core.models.connection_log import ConnectionLog
from app.features.chat.models.conversation import Conversation, Message
from app.core.utils import now

pytestmark = pytest.mark.asyncio


async def _agency(session, **fields):
    ag = Agency(name=fields.pop("name", "Test Agency"), **fields)
    session.add(ag)
    await session.flush()
    return ag


async def _conversation(session):
    conv = Conversation()
    session.add(conv)
    await session.flush()
    return conv


async def _message(session, conv, **fields):
    msg = Message(conversation_id=conv.id, role=fields.pop("role", "user"),
                  content=fields.pop("content", "hi"), **fields)
    session.add(msg)
    await session.flush()
    return msg


async def test_get_dashboard_stats_shape(db_session):
    from app.features.analytics.services import dashboard

    ag = await _agency(db_session, color="#fff", total_calls=10)
    conv = await _conversation(db_session)
    await _message(db_session, conv, role="user")
    await _message(db_session, conv, role="assistant", rating="up")
    await _message(db_session, conv, role="user", category="สอบถามข้อมูล")

    result = await dashboard.get_dashboard_stats(db_session)

    assert set(result.keys()) == {"stats", "agencyUsage", "weeklyTrend", "categoryData"}
    assert len(result["weeklyTrend"]) == 7
    assert result["stats"]["totalQuestions"] == 2
    assert {"name": "Test Agency", "value": 10, "fill": "#fff"} in result["agencyUsage"]
    assert {"category": "สอบถามข้อมูล", "count": 1} in result["categoryData"]


async def test_get_agency_health_empty_agencies(db_session):
    from app.features.analytics.schemas.insight import AgencyHealthData
    from app.features.analytics.services import health

    result = await health.get_agency_health(db_session)

    assert isinstance(result, AgencyHealthData)
    assert result.agencies == []
    assert result.historical == []


async def test_get_agency_health_computes_latency_and_error_rate(db_session):
    from app.features.analytics.schemas.insight import AgencyHealthData
    from app.features.analytics.services import health

    ag = await _agency(db_session, short_name="TA", status="active")
    db_session.add_all([
        ConnectionLog(agency_id=ag.id, connection_type="API", status="success", latency_ms=100),
        ConnectionLog(agency_id=ag.id, connection_type="API", status="success", latency_ms=200),
    ])
    await db_session.flush()

    with patch.object(health, "error_window", new=AsyncMock(return_value=(10, 1))):
        result = await health.get_agency_health(db_session)

    assert isinstance(result, AgencyHealthData)
    assert len(result.agencies) == 1
    entry = result.agencies[0]
    assert entry.id == str(ag.id)
    assert entry.status == "healthy"
    assert entry.errorRate == 10.0
    assert entry.uptime == 90.0


async def test_get_usage_heatmap_shape(db_session):
    from app.features.analytics.schemas.insight import UsageHeatmapData
    from app.features.analytics.services import heatmap

    ag = await _agency(db_session)
    conv = await _conversation(db_session)
    await _message(db_session, conv, role="user", agency_ids=[str(ag.id)])

    result = await heatmap.get_usage_heatmap(db_session, "7d")

    assert isinstance(result, UsageHeatmapData)
    assert result.range == "7d"
    assert result.totalMessages == 1
    assert len(result.dayHourMatrix) == 7
    assert len(result.hourlyByAgency) == 1


async def test_get_executive_summary_smoke(db_session):
    from app.features.analytics.schemas.executive_summary import ExecutiveData
    from app.features.analytics.services import brief

    with patch.object(brief, "_latest_brief", new=AsyncMock(return_value="brief")):
        result = await brief.get_executive_summary(db_session)

    assert isinstance(result, ExecutiveData)
    assert result.weeklyBrief == "brief"


async def test_latest_brief_returns_placeholder_when_table_empty(db_session):
    from app.features.analytics.services import brief

    result = await brief._latest_brief(db_session)

    assert result == brief._BRIEF_PLACEHOLDER


async def test_regenerate_weekly_brief_persists_ok_row(db_session):
    from app.features.analytics.services import brief
    from app.features.llm.services import LlmResult, LlmUsageInfo

    llm_result = LlmResult(
        content="generated brief", tool_calls=None,
        usage=LlmUsageInfo(model="m", prompt_tokens=0, completion_tokens=0, cost_usd=None),
        raw={},
    )

    with patch("app.features.llm.services.chat", new=AsyncMock(return_value=llm_result)):
        result = await brief.regenerate_weekly_brief(db_session)

    assert result.status == "ok"
    assert result.content == "generated brief"


async def test_regenerate_weekly_brief_calls_chat_with_session(db_session):
    """chat() is session-first; regenerate_weekly_brief must thread its session through."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.features.analytics.services import brief
    from app.features.llm.services import LlmResult, LlmUsageInfo

    llm_result = LlmResult(
        content="generated brief", tool_calls=None,
        usage=LlmUsageInfo(model="m", prompt_tokens=0, completion_tokens=0, cost_usd=None),
        raw={},
    )
    fake_chat = AsyncMock(return_value=llm_result)

    with patch("app.features.llm.services.chat", new=fake_chat):
        await brief.regenerate_weekly_brief(db_session)

    assert isinstance(fake_chat.call_args.args[0], AsyncSession)


async def test_regenerate_weekly_brief_persists_error_row_on_llm_failure(db_session):
    from app.features.analytics.services import brief

    with patch("app.features.llm.services.chat", new=AsyncMock(side_effect=RuntimeError("network error"))):
        result = await brief.regenerate_weekly_brief(db_session)

    assert result.status == "error"
    assert result.content == brief._BRIEF_FALLBACK


async def test_get_executive_summary_january_month_boundary(db_session):
    """prev_month must be 12 in January, not 0 — verified via the actual EXTRACT(month) query."""
    import datetime as dt
    from app.features.analytics.services import brief

    jan_15 = dt.datetime(2026, 1, 15, tzinfo=dt.timezone.utc)
    captured_months = []
    original = brief._count_by_calendar_part

    async def _spy(session, model, unit, value, *extra):
        if unit == "month":
            captured_months.append(value)
        return await original(session, model, unit, value, *extra)

    with (
        patch.object(brief, "now", return_value=jan_15),
        patch.object(brief, "_latest_brief", new=AsyncMock(return_value="brief")),
        patch.object(brief, "_count_by_calendar_part", new=_spy),
    ):
        await brief.get_executive_summary(db_session)

    assert 0 not in captured_months, f"Invalid month 0 found: {captured_months}"
    assert 12 in captured_months, f"Expected December (12) for prev_month in January, got: {captured_months}"
