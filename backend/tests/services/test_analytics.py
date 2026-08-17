from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _AsyncCM:
    """Stand-in for `async with in_transaction() as conn`."""

    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *args):
        return False


def _make_query_mock(count_values=None, values_values=None):
    """Chainable Tortoise queryset mock.

    filter/annotate/group_by return self; count/values pop from the provided lists.
    """
    m = MagicMock()
    m.filter.return_value = m
    m.annotate.return_value = m
    m.group_by.return_value = m
    m.count = AsyncMock(side_effect=list(count_values or []))
    m.values = AsyncMock(side_effect=list(values_values or []))
    return m


@pytest.mark.asyncio
async def test_get_dashboard_stats_shape():
    from app.services.analytics import dashboard

    conn = MagicMock()
    conn.execute_query = AsyncMock()
    conn.execute_query_dict = AsyncMock(return_value=[{"dow": 1, "questions": 4}])

    # Call order in get_dashboard_stats:
    # count x2: totalQuestions, todayQuestions
    # values x3: avg_time, rate, categories
    msg = _make_query_mock(
        count_values=[5, 2],
        values_values=[
            [{"avg_time": 1500}],
            [{"rate": 80}],
            [{"category": "x", "cnt": 3}],
        ],
    )
    agency = MagicMock()
    agency.all.return_value = MagicMock(
        values=AsyncMock(return_value=[{"name": "A", "color": "#fff", "total_calls": 10}])
    )

    with (
        patch.object(dashboard, "in_transaction", return_value=_AsyncCM(conn)),
        patch.object(dashboard, "Message", msg),
        patch.object(dashboard, "Agency", agency),
    ):
        result = await dashboard.get_dashboard_stats()

    assert set(result.keys()) == {"stats", "agencyUsage", "weeklyTrend", "categoryData"}
    assert len(result["weeklyTrend"]) == 7
    assert result["stats"]["totalQuestions"] == 5
    assert result["stats"]["todayQuestions"] == 2
    assert result["agencyUsage"] == [{"name": "A", "value": 10, "fill": "#fff"}]
    assert result["categoryData"] == [{"category": "x", "count": 3}]


@pytest.mark.asyncio
async def test_get_agency_health_empty_agencies():
    from app.schemas.insight import AgencyHealthData
    from app.services.analytics import health

    conn = MagicMock()
    conn.execute_query = AsyncMock()
    # No agencies -> returns early; no DB queries beyond the SET TIME ZONE and Agency.all
    conn.execute_query_dict = AsyncMock(return_value=[])

    agency = MagicMock()
    agency.all.return_value = MagicMock(values=AsyncMock(return_value=[]))

    with (
        patch.object(health, "in_transaction", return_value=_AsyncCM(conn)),
        patch.object(health, "Agency", agency),
    ):
        result = await health.get_agency_health()

    assert isinstance(result, AgencyHealthData)
    assert result.agencies == []
    assert result.historical == []


@pytest.mark.asyncio
async def test_get_executive_summary_smoke():
    from app.schemas.executive_summary import ExecutiveData
    from app.services.analytics import brief

    conn = MagicMock()
    conn.execute_query = AsyncMock()

    # Message.filter(...).count() is called 4 times (thisMonth, lastMonth, thisYear, lastYear).
    # Message.annotate(...).filter(...).group_by(...).annotate(...)x3.values(...) once (monthlyTrend).
    # Using fixed return_value=0 / [] so call order doesn't matter.
    msg = MagicMock()
    msg.filter.return_value = msg
    msg.annotate.return_value = msg
    msg.group_by.return_value = msg
    msg.count = AsyncMock(return_value=0)
    msg.values = AsyncMock(return_value=[])

    conv = MagicMock()
    conv.filter.return_value = conv
    conv.count = AsyncMock(return_value=0)

    chat_mock = AsyncMock()

    with (
        patch.object(brief, "in_transaction", return_value=_AsyncCM(conn)),
        patch.object(brief, "Message", msg),
        patch.object(brief, "Conversation", conv),
        patch.object(brief, "_latest_brief", new=AsyncMock(return_value="brief")),
        patch("app.services.llm.chat", chat_mock),
    ):
        result = await brief.get_executive_summary()

    assert isinstance(result, ExecutiveData)
    assert result.weeklyBrief == "brief"
    # GET must read the cached brief from the DB and never call the LLM.
    chat_mock.assert_not_called()


@pytest.mark.asyncio
async def test_latest_brief_returns_placeholder_when_table_empty():
    from app.services.analytics import brief

    qs = MagicMock()
    qs.order_by.return_value = qs
    qs.first = AsyncMock(return_value=None)
    brief_model = MagicMock()
    brief_model.all.return_value = qs

    with patch.object(brief, "ExecutiveBrief", brief_model):
        result = await brief._latest_brief()

    assert result == brief._BRIEF_PLACEHOLDER


@pytest.mark.asyncio
async def test_regenerate_weekly_brief_persists_ok_row():
    from app.services.analytics import brief

    from app.services.llm import LlmResult, LlmUsageInfo

    created = MagicMock(content="generated brief", status="ok")
    brief_model = MagicMock()
    brief_model.create = AsyncMock(return_value=created)

    llm_result = LlmResult(
        content="generated brief", tool_calls=None,
        usage=LlmUsageInfo(model="m", prompt_tokens=0, completion_tokens=0, cost_usd=None),
        raw={},
    )

    with (
        patch.object(brief, "_compute_executive_metrics", new=AsyncMock(return_value={})),
        patch.object(brief, "_build_brief_prompt", return_value="prompt"),
        patch.object(brief, "ExecutiveBrief", brief_model),
        patch("app.services.llm.chat", new=AsyncMock(return_value=llm_result)),
    ):
        result = await brief.regenerate_weekly_brief()

    brief_model.create.assert_awaited_once()
    kwargs = brief_model.create.await_args.kwargs
    assert kwargs["status"] == "ok"
    assert kwargs["content"] == "generated brief"
    assert result is created


@pytest.mark.asyncio
async def test_regenerate_weekly_brief_persists_error_row_on_http_failure():
    from app.services.analytics import brief

    brief_model = MagicMock()
    brief_model.create = AsyncMock(return_value=MagicMock())

    with (
        patch.object(brief, "_compute_executive_metrics", new=AsyncMock(return_value={})),
        patch.object(brief, "_build_brief_prompt", return_value="prompt"),
        patch.object(brief, "ExecutiveBrief", brief_model),
        patch("app.services.llm.chat", new=AsyncMock(side_effect=RuntimeError("network error"))),
    ):
        await brief.regenerate_weekly_brief()

    kwargs = brief_model.create.await_args.kwargs
    assert kwargs["status"] == "error"
    assert kwargs["content"] == brief._BRIEF_FALLBACK


@pytest.mark.asyncio
async def test_get_agency_health_error_rate_and_uptime_values():
    """uptime/errorRate come from error_window (24h, reset-aware): 1/10 -> 10.0% / 90.0%."""
    from app.schemas.insight import AgencyHealthData
    from app.services.analytics import health

    conn = MagicMock()
    conn.execute_query = AsyncMock()
    conn.capabilities.dialect = "sqlite"

    # Grouped-query call order (all via conn.execute_query_dict):
    #   [0] currentLatency  GROUP BY agency_id
    #   [1] avgLatency      GROUP BY agency_id
    #   [2] dayCount        GROUP BY agency_id
    # errorRate/uptime no longer use SQL — they come from error_window().
    conn.execute_query_dict = AsyncMock(side_effect=[
        [{"agency_id": "ag-1", "avg_latency": 100}],
        [{"agency_id": "ag-1", "avg_latency": 120}],
        [{"agency_id": "ag-1", "total": 4320}],
    ])

    agency = MagicMock()
    agency.all.return_value = MagicMock(values=AsyncMock(return_value=[
        {"id": "ag-1", "name": "A", "short_name": "A", "status": "active", "stats_reset_at": None},
    ]))

    # rawHistorical still uses the ConnectionLog ORM queryset
    conn_log = _make_query_mock(values_values=[[]])
    ew = AsyncMock(return_value=(10, 1))  # (checks, failures) over trailing 24h

    with patch.object(health, "in_transaction", return_value=_AsyncCM(conn)), \
         patch.object(health, "Agency", agency), \
         patch.object(health, "error_window", ew), \
         patch.object(health, "ConnectionLog", conn_log):
        result = await health.get_agency_health()

    assert isinstance(result, AgencyHealthData)
    ag = result.agencies[0]
    assert ag.errorRate == 10.0
    assert ag.uptime == 90.0
    ew.assert_awaited_once_with("ag-1", None)


@pytest.mark.asyncio
async def test_get_agency_health_honors_stats_reset_at_and_two_dp():
    import datetime

    from app.schemas.insight import AgencyHealthData
    from app.services.analytics import health

    reset = datetime.datetime(2026, 6, 30, 9, 0, tzinfo=datetime.timezone.utc)

    conn = MagicMock()
    conn.execute_query = AsyncMock()
    conn.capabilities.dialect = "sqlite"
    conn.execute_query_dict = AsyncMock(side_effect=[
        [{"agency_id": "ag-1", "avg_latency": 100}],  # currentLatency
        [{"agency_id": "ag-1", "avg_latency": 120}],  # avgLatency
        [{"agency_id": "ag-1", "total": 4320}],       # dayCount
    ])

    agency = MagicMock()
    agency.all.return_value = MagicMock(values=AsyncMock(return_value=[
        {"id": "ag-1", "name": "A", "short_name": "A", "status": "active", "stats_reset_at": reset},
    ]))

    conn_log = _make_query_mock(values_values=[[]])
    # 1 failure out of 3 -> error_rate 33.3333..%, uptime 66.6666..% -> 2 dp.
    ew = AsyncMock(return_value=(3, 1))

    with patch.object(health, "in_transaction", return_value=_AsyncCM(conn)), \
         patch.object(health, "Agency", agency), \
         patch.object(health, "error_window", ew), \
         patch.object(health, "ConnectionLog", conn_log):
        result = await health.get_agency_health()

    assert isinstance(result, AgencyHealthData)
    ag = result.agencies[0]
    assert ag.errorRate == 33.33
    assert ag.uptime == 66.67
    ew.assert_awaited_once_with("ag-1", reset)


@pytest.mark.asyncio
async def test_get_agency_health_two_agencies_grouped():
    from app.schemas.insight import AgencyHealthData
    from app.services.analytics import health

    conn = MagicMock()
    conn.execute_query = AsyncMock()
    conn.capabilities.dialect = "sqlite"

    # ag-1: 200ms cur latency, 180ms avg, 2/20 errors, 2880 requests/day
    # ag-2: 50ms cur latency, 60ms avg, 0/5 errors, 720 requests/day
    conn.execute_query_dict = AsyncMock(side_effect=[
        # currentLatency
        [{"agency_id": "ag-1", "avg_latency": 200}, {"agency_id": "ag-2", "avg_latency": 50}],
        # avgLatency (7d)
        [{"agency_id": "ag-1", "avg_latency": 180}, {"agency_id": "ag-2", "avg_latency": 60}],
        # dayCount
        [{"agency_id": "ag-1", "total": 2880}, {"agency_id": "ag-2", "total": 720}],
    ])

    agency = MagicMock()
    agency.all.return_value = MagicMock(values=AsyncMock(return_value=[
        {"id": "ag-1", "name": "Agency One", "short_name": "A1", "status": "active", "stats_reset_at": None},
        {"id": "ag-2", "name": "Agency Two", "short_name": "A2", "status": "inactive", "stats_reset_at": None},
    ]))

    conn_log = _make_query_mock(values_values=[[]])
    # error_window over trailing 24h: ag-1 -> 2/20, ag-2 -> 0/5.
    windows = {"ag-1": (20, 2), "ag-2": (5, 0)}

    async def _error_window(agency_id, reset_at=None):
        return windows[agency_id]

    with patch.object(health, "in_transaction", return_value=_AsyncCM(conn)), \
         patch.object(health, "Agency", agency), \
         patch.object(health, "error_window", _error_window), \
         patch.object(health, "ConnectionLog", conn_log):
        result = await health.get_agency_health()

    assert isinstance(result, AgencyHealthData)
    assert len(result.agencies) == 2

    a1 = next(a for a in result.agencies if a.id == "ag-1")
    a2 = next(a for a in result.agencies if a.id == "ag-2")

    assert a1.errorRate == 10.0
    assert a1.uptime == 90.0
    assert a1.currentLatency == 200.0
    assert a1.avgLatency == 180.0
    assert a1.status == "healthy"

    assert a2.errorRate == 0.0
    assert a2.uptime == 100.0
    assert a2.currentLatency == 50.0
    assert a2.avgLatency == 60.0
    assert a2.status == "down"


@pytest.mark.asyncio
async def test_get_executive_summary_january_month_boundary():
    """prev_month must be 12 in January, not 0."""
    from app.services.analytics import brief
    from unittest.mock import patch as _patch
    import datetime

    # Freeze time to January 15.
    jan_15 = datetime.datetime(2026, 1, 15, tzinfo=datetime.timezone.utc)

    conn = MagicMock()
    conn.execute_query = AsyncMock()

    msg = MagicMock()
    msg.filter.return_value = msg
    msg.annotate.return_value = msg
    msg.group_by.return_value = msg
    msg.count = AsyncMock(return_value=0)
    msg.values = AsyncMock(return_value=[])

    conv = MagicMock()
    conv.filter.return_value = conv
    conv.count = AsyncMock(return_value=0)

    # Capture the month keyword arg passed to Message.filter for lastMonthQuestions.
    captured_months = []
    original_filter = msg.filter

    def _capturing_filter(**kwargs):
        if "created_at__month" in kwargs:
            captured_months.append(kwargs["created_at__month"])
        return msg

    msg.filter.side_effect = _capturing_filter

    with (
        _patch.object(brief, "in_transaction", return_value=_AsyncCM(conn)),
        _patch.object(brief, "Message", msg),
        _patch.object(brief, "Conversation", conv),
        _patch.object(brief, "_latest_brief", new=AsyncMock(return_value="brief")),
        _patch("app.services.analytics.brief.now", return_value=jan_15),
    ):
        await brief.get_executive_summary()

    # All captured month values must be valid (1-12); 0 must never appear.
    assert 0 not in captured_months, f"Invalid month 0 found in filter calls: {captured_months}"
    assert 12 in captured_months, f"Expected December (12) for prev_month in January, got: {captured_months}"
