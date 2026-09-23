import pytest

from app.features.agency.models.agency import Agency
from app.features.analytics.repositories import public_status_read as repo

pytestmark = pytest.mark.asyncio


async def test_list_public_agencies_excludes_draft_ordered_by_name(db_session):
    db_session.add_all([
        Agency(name="Zebra Office", status="active"),
        Agency(name="Alpha Office", status="active"),
        Agency(name="Draft Office", status="draft"),
    ])
    await db_session.flush()

    agencies = await repo.list_public_agencies(db_session)

    names = [a.name for a in agencies]
    assert names == ["Alpha Office", "Zebra Office"]
