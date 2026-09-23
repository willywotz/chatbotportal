import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def test_monitoring_tables_exist(db_session):
    rows = (await db_session.execute(text(
        "select table_name from information_schema.tables where table_schema='public'"
    ))).scalars().all()
    assert {"agency_check_state", "uptime_bucket", "incidents"} <= set(rows)


async def test_partial_unique_open_incident(db_session):
    idx = (await db_session.execute(text(
        "select indexname from pg_indexes where tablename='incidents'"
    ))).scalars().all()
    assert "uq_incident_open_per_agency" in idx
