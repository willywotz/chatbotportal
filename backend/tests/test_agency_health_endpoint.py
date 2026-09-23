import pytest

from app.features.agency.repositories import agency as agency_repo
from app.core.repositories import connection_log as connection_log_repo
from app.features.agency import routers as r


@pytest.mark.asyncio
async def test_health_history_endpoint(db_session):
    ag = await agency_repo.create(db_session, name="A", short_name="A", connection_type="API", status="active")
    await connection_log_repo.create(
        db_session, agency_id=ag.id, action="test", connection_type="API",
        status="success", latency_ms=200, detail="",
    )
    res = await r.agency_health_history(ag.id, window="24h", session=db_session)
    assert len(res.data) == 24
    assert res.data[0].checks >= 0


@pytest.mark.asyncio
async def test_health_history_404(db_session):
    import uuid
    from app.core.errors import ApiError
    with pytest.raises(ApiError) as exc:
        await r.agency_health_history(uuid.uuid4(), window="24h", session=db_session)
    assert exc.value.status == 404
