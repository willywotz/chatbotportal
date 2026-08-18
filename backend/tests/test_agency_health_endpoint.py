import pytest

from app.models import Agency, ConnectionLog
from app.routers import agencies as r


@pytest.mark.asyncio
async def test_health_history_endpoint(db):
    ag = await Agency.create(name="A", short_name="A", connection_type="API", status="active")
    await ConnectionLog.create(agency=ag, action="test", connection_type="API", status="success", latency_ms=200, detail="")
    res = await r.agency_health_history(ag.id, window="24h")
    assert len(res.data) == 24
    assert res.data[0].checks >= 0


@pytest.mark.asyncio
async def test_health_history_404(db):
    import uuid
    from app.errors import ApiError
    with pytest.raises(ApiError) as exc:
        await r.agency_health_history(uuid.uuid4(), window="24h")
    assert exc.value.status == 404
