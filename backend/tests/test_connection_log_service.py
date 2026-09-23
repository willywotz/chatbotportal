"""Service-layer tests for connection-log queries (moved out of the router)."""
import uuid

import pytest

from app.errors import ApiError
from app.models.agency import Agency
from app.models.connection_log import ConnectionLog
from app.services import connection_log as connection_log_service

pytestmark = pytest.mark.asyncio


async def _agency(session, **fields):
    ag = Agency(name="A", status="active", **fields)
    session.add(ag)
    await session.flush()
    return ag


async def test_list_logs_filters_and_stats(db_session):
    ag = await _agency(db_session)
    db_session.add_all([
        ConnectionLog(agency_id=ag.id, connection_type="API", status="success", action="test"),
        ConnectionLog(agency_id=ag.id, connection_type="API", status="error", action="test"),
        ConnectionLog(agency_id=ag.id, connection_type="MCP", status="success", action="test"),
    ])
    await db_session.flush()

    logs, stats = await connection_log_service.list_logs(
        db_session, search=None, agency_id=None, status_filter="success", connection_type="API",
        include_test=True, page=1, limit=20,
    )

    assert len(logs) == 1
    assert stats["total_items"] == 1
    assert stats["successful_connections"] == 1
    assert stats["failed_connections"] == 0


async def test_list_logs_invalid_agency_id_raises_400(db_session):
    with pytest.raises(ApiError) as exc:
        await connection_log_service.list_logs(
            db_session, search=None, agency_id="not-a-uuid", status_filter=None, connection_type=None,
            include_test=True, page=1, limit=20,
        )
    assert exc.value.status == 400


async def test_get_stats_excludes_test_action_by_default(db_session):
    ag = await _agency(db_session)
    db_session.add_all([
        ConnectionLog(agency_id=ag.id, connection_type="API", status="success", action="test"),
        ConnectionLog(agency_id=ag.id, connection_type="API", status="success", action="query"),
    ])
    await db_session.flush()

    stats = await connection_log_service.get_stats(db_session, include_test=False)

    assert stats["total_connections"] == 1


async def test_get_log_missing_raises_404(db_session):
    with pytest.raises(ApiError) as exc:
        await connection_log_service.get_log(db_session, str(uuid.uuid4()))
    assert exc.value.status == 404
