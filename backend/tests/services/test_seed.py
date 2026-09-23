import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.features.agency.services import seed

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _bind_seed_session(db_session, monkeypatch):
    """run_seed_agencies opens its own session; bind it to the test's connection
    (same DB transaction) so writes are visible/rolled back with the test."""
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(seed, "AsyncSessionLocal", factory)


async def test_run_seed_agencies_creates_defaults_once(db_session):
    result = await seed.run_seed_agencies()
    assert result["status"] == "created"
    assert result["agencies"] == [a["name"] for a in seed.DEFAULT_AGENCIES]

    again = await seed.run_seed_agencies()
    assert again["status"] == "skipped"
