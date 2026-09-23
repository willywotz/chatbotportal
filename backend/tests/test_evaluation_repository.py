import pytest

from app.features.agency.repositories import agency as agency_repo
from app.features.agency.repositories import evaluation as evaluation_repo
from app.features.agency.models.evaluation import GoldenQuestion

pytestmark = pytest.mark.asyncio


async def test_all_golden_with_agency_loads_agency(db_session):
    agency = await agency_repo.create(db_session, name="Agency A")
    gq = GoldenQuestion(agency_id=agency.id, question="Q?", expected_topics=["a"])
    db_session.add(gq)
    await db_session.flush()

    rows = await evaluation_repo.all_golden_with_agency(db_session)
    assert len(rows) == 1
    assert rows[0].agency.name == "Agency A"
