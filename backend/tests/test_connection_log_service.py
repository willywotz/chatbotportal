"""Service-layer tests for connection-log queries (moved out of the router)."""
from app.errors import ApiError
from app.models import Agency, ConnectionLog
from app.services import connection_log as connection_log_service


async def test_list_logs_filters_and_stats(db):
    ag = await Agency.create(name="A", status="active")
    await ConnectionLog.create(agency=ag, connection_type="API", status="success", action="test")
    await ConnectionLog.create(agency=ag, connection_type="API", status="error", action="test")
    await ConnectionLog.create(agency=ag, connection_type="MCP", status="success", action="test")

    logs, stats = await connection_log_service.list_logs(
        search=None, agency_id=None, status_filter="success", connection_type="API",
        include_test=True, page=1, limit=20,
    )

    assert len(logs) == 1
    assert stats["total_items"] == 1
    assert stats["successful_connections"] == 1
    assert stats["failed_connections"] == 0


async def test_list_logs_invalid_agency_id_raises_400(db):
    try:
        await connection_log_service.list_logs(
            search=None, agency_id="not-a-uuid", status_filter=None, connection_type=None,
            include_test=True, page=1, limit=20,
        )
        assert False, "expected ApiError"
    except ApiError as exc:
        assert exc.status == 400


async def test_get_stats_excludes_test_action_by_default(db):
    ag = await Agency.create(name="A", status="active")
    await ConnectionLog.create(agency=ag, connection_type="API", status="success", action="test")
    await ConnectionLog.create(agency=ag, connection_type="API", status="success", action="query")

    stats = await connection_log_service.get_stats(include_test=False)

    assert stats["total_connections"] == 1


async def test_get_log_missing_raises_404(db):
    import uuid
    try:
        await connection_log_service.get_log(str(uuid.uuid4()))
        assert False, "expected ApiError"
    except ApiError as exc:
        assert exc.status == 404
