import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def test_pgroonga_available(db_session):
    row = (await db_session.execute(
        text("SELECT extname FROM pg_extension WHERE extname='pgroonga'")
    )).scalar_one_or_none()
    assert row == "pgroonga"
