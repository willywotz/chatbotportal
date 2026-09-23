from datetime import timedelta

import pytest

from app.features.agency.models.agency import Agency
from app.core.models.connection_log import ConnectionLog
from app.features.chat.models.conversation import Conversation, Message
from app.features.llm.models.llm_usage import LlmUsage
from app.features.analytics.repositories import analytics as repo
from app.core.utils import now

pytestmark = pytest.mark.asyncio


async def _agency(session, **fields):
    ag = Agency(name="Test Agency", **fields)
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


async def test_connection_log_avg_latency_by_agency(db_session):
    ag = await _agency(db_session)
    since = now() - timedelta(hours=1)
    session = db_session
    session.add_all([
        ConnectionLog(agency_id=ag.id, connection_type="API", status="success", latency_ms=100),
        ConnectionLog(agency_id=ag.id, connection_type="API", status="success", latency_ms=200),
    ])
    await session.flush()

    result = await repo.connection_log_avg_latency_by_agency(session, since)

    assert result[str(ag.id)] == pytest.approx(150.0)


async def test_connection_log_count_by_agency(db_session):
    ag = await _agency(db_session)
    since = now() - timedelta(hours=1)
    db_session.add_all([
        ConnectionLog(agency_id=ag.id, connection_type="API", status="success"),
        ConnectionLog(agency_id=ag.id, connection_type="API", status="error"),
    ])
    await db_session.flush()

    result = await repo.connection_log_count_by_agency(db_session, since)

    assert result[str(ag.id)] == 2


async def test_connection_log_historical_buckets_by_date_and_agency(db_session):
    ag = await _agency(db_session)
    since = now() - timedelta(days=1)
    db_session.add_all([
        ConnectionLog(agency_id=ag.id, connection_type="API", status="success", latency_ms=100),
        ConnectionLog(agency_id=ag.id, connection_type="API", status="error", latency_ms=300),
    ])
    await db_session.flush()

    rows = await repo.connection_log_historical(db_session, since)

    assert len(rows) == 1
    row = rows[0]
    assert row["agency_id"] == ag.id
    assert row["latency"] == pytest.approx(200.0)
    assert row["uptime"] == pytest.approx(50.0)


async def test_list_agencies_health_summary(db_session):
    ag = await _agency(db_session, short_name="TA", status="active")

    rows = await repo.list_agencies_health_summary(db_session)

    assert {"id": ag.id, "name": "Test Agency", "short_name": "TA",
            "status": "active", "stats_reset_at": None} in rows


async def test_list_agencies_usage(db_session):
    ag = await _agency(db_session, color="#fff", total_calls=5)

    rows = await repo.list_agencies_usage(db_session)

    assert {"name": "Test Agency", "color": "#fff", "total_calls": 5} in rows


async def test_list_agencies_basic(db_session):
    ag = await _agency(db_session)

    rows = await repo.list_agencies_basic(db_session)

    assert {"id": ag.id, "name": "Test Agency"} in rows


async def test_connection_log_stats_counts_and_latency(db_session):
    since = now() - timedelta(hours=1)
    db_session.add_all([
        ConnectionLog(connection_type="API", status="success", action="query", latency_ms=100),
        ConnectionLog(connection_type="API", status="error", action="query", latency_ms=300),
        ConnectionLog(connection_type="API", status="success", action="test", latency_ms=999),
    ])
    await db_session.flush()

    stats = await repo.connection_log_stats(db_session, since=since)

    assert stats == {
        "total_connections": 2,
        "successful_connections": 1,
        "failed_connections": 1,
        "average_latency_ms": 200,
    }


async def test_connection_log_stats_include_test(db_session):
    since = now() - timedelta(hours=1)
    db_session.add(ConnectionLog(connection_type="API", status="success", action="test", latency_ms=50))
    await db_session.flush()

    stats = await repo.connection_log_stats(db_session, since=since, include_test=True)

    assert stats["total_connections"] == 1
    assert stats["average_latency_ms"] == 50


async def test_message_role_count(db_session):
    conv = await _conversation(db_session)
    await _message(db_session, conv, role="user")
    await _message(db_session, conv, role="assistant")

    assert await repo.message_role_count(db_session, "user") == 1


async def test_message_role_count_with_window(db_session):
    conv = await _conversation(db_session)
    old = now() - timedelta(days=10)
    await _message(db_session, conv, role="user", created_at=old)
    await _message(db_session, conv, role="user")

    since = now() - timedelta(days=1)
    assert await repo.message_role_count(db_session, "user", since=since) == 1


async def test_conversation_count(db_session):
    await _conversation(db_session)
    await _conversation(db_session)

    assert await repo.conversation_count(db_session) == 2


async def test_message_weekly_dow_counts(db_session):
    conv = await _conversation(db_session)
    await _message(db_session, conv, role="user")

    result = await repo.message_weekly_dow_counts(db_session)

    dow = now().weekday()  # Python Monday=0; Postgres DOW Sunday=0 — just check total count.
    assert sum(result.values()) == 1


async def test_message_avg_response_time_ms(db_session):
    conv = await _conversation(db_session)
    await _message(db_session, conv, response_time=1000)
    await _message(db_session, conv, response_time=2000)

    result = await repo.message_avg_response_time_ms(db_session)

    assert result == pytest.approx(1.5)


async def test_message_satisfaction_rate(db_session):
    conv = await _conversation(db_session)
    await _message(db_session, conv, rating="up")
    await _message(db_session, conv, rating="down")
    await _message(db_session, conv, rating=None)

    result = await repo.message_satisfaction_rate(db_session)

    assert result == pytest.approx(50.0)


async def test_message_category_counts(db_session):
    conv = await _conversation(db_session)
    await _message(db_session, conv, category="สอบถามข้อมูล")
    await _message(db_session, conv, category="สอบถามข้อมูล")
    await _message(db_session, conv, category="กฎหมาย")

    rows = await repo.message_category_counts(db_session)

    by_category = {r["category"]: r["cnt"] for r in rows}
    assert by_category == {"สอบถามข้อมูล": 2, "กฎหมาย": 1}


async def test_message_hourly_by_agency(db_session):
    conv = await _conversation(db_session)
    ts = now().replace(hour=10, minute=0, second=0, microsecond=0)
    await _message(db_session, conv, agency_ids=["ag-1"], created_at=ts)

    since = now() - timedelta(days=1)
    rows = await repo.message_hourly_by_agency(db_session, since)

    assert any(r["agency_ids"] == ["ag-1"] and int(r["hour"]) == 10 and r["cnt"] == 1 for r in rows)


async def test_message_day_hour_matrix(db_session):
    conv = await _conversation(db_session)
    ts = now().replace(hour=9, minute=0, second=0, microsecond=0)
    await _message(db_session, conv, role="user", created_at=ts)

    since = now() - timedelta(days=1)
    rows = await repo.message_day_hour_matrix(db_session, since)

    assert any(int(r["hour"]) == 9 and r["cnt"] == 1 for r in rows)


async def test_message_peak_day_and_hour_ordered_desc(db_session):
    conv = await _conversation(db_session)
    ts = now().replace(hour=14, minute=0, second=0, microsecond=0)
    await _message(db_session, conv, role="user", created_at=ts)
    await _message(db_session, conv, role="user", created_at=ts)
    # A day earlier is always a different weekday, so this lands in a different DOW bucket.
    other = (now() - timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)
    await _message(db_session, conv, role="user", created_at=other)

    since = now() - timedelta(days=7)
    peak_hour = await repo.message_peak_hour(db_session, since)
    peak_day = await repo.message_peak_day(db_session, since)

    assert int(peak_hour[0]["hour"]) == 14
    assert peak_hour[0]["cnt"] == 2
    assert peak_day[0]["cnt"] == 2


async def test_message_monthly_trend(db_session):
    conv = await _conversation(db_session)
    ts = now()
    await _message(db_session, conv, role="user", rating="up", created_at=ts)
    await _message(db_session, conv, role="assistant", rating="down", created_at=ts)

    since = now() - timedelta(days=365)
    rows = await repo.message_monthly_trend(db_session, since)

    assert len(rows) == 1
    assert rows[0]["questions"] == 1
    assert rows[0]["rating_up"] == 1
    assert rows[0]["rating_down"] == 1


async def test_llm_usage_summary_grouped_by_purpose(db_session):
    db_session.add_all([
        LlmUsage(model="gpt", purpose="chat", prompt_tokens=10, completion_tokens=5, cost_usd=0.01),
        LlmUsage(model="gpt", purpose="chat", prompt_tokens=20, completion_tokens=10, cost_usd=0.02),
        LlmUsage(model="gpt", purpose="brief", prompt_tokens=1, completion_tokens=1, cost_usd=0.001),
    ])
    await db_session.flush()

    rows = await repo.llm_usage_summary(db_session, "purpose")

    by_purpose = {r["purpose"]: r for r in rows}
    assert by_purpose["chat"]["prompt"] == 30
    assert by_purpose["chat"]["completion"] == 15
    assert by_purpose["chat"]["cost"] == pytest.approx(0.03)
    assert by_purpose["brief"]["prompt"] == 1
