import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import event_consumers
from app.core.repositories import audit as audit_repo

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _bind(db_session, monkeypatch):
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(event_consumers, "AsyncSessionLocal", factory)


async def test_incident_opened_projects_to_audit(db_session):
    await event_consumers._on_incident_opened({"agency_id": "00000000-0000-0000-0000-0000000000aa",
                                               "incident_id": "00000000-0000-0000-0000-0000000000bb"})
    rows, total = await audit_repo.list_and_count(
        db_session, action="agency.incident_opened", object_type=None, actor=None, offset=0, limit=10,
    )
    assert total == 1


def test_incident_consumers_registered():
    from app.core import events
    events._HANDLERS.clear()
    event_consumers._registered = False
    event_consumers.register_consumers()
    assert "agency.incident_opened" in events._HANDLERS
    assert "agency.incident_closed" in events._HANDLERS
