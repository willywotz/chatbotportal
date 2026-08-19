import pytest

from app.repositories import agency as agency_repo
from app.repositories import popular_question as pq_repo

pytestmark = pytest.mark.asyncio


async def test_create_and_text_key_exists(db_session):
    pq = await pq_repo.create(db_session, text="Q1", text_key="q1")
    assert pq.text == "Q1"
    assert await pq_repo.text_key_exists(db_session, "q1") is True
    assert await pq_repo.text_key_exists(db_session, "nope") is False


async def test_visible_with_agency_excludes_hidden_and_loads_agency(db_session):
    agency = await agency_repo.create(db_session, name="Agency A")
    await pq_repo.create(db_session, text="visible", text_key="v1", agency_id=agency.id)
    await pq_repo.create(db_session, text="hidden", text_key="h1", hidden=True)
    await db_session.flush()

    rows = await pq_repo.visible_with_agency(db_session)
    assert [r.text for r in rows] == ["visible"]
    assert rows[0].agency.name == "Agency A"


async def test_all_with_agency_includes_hidden(db_session):
    await pq_repo.create(db_session, text="visible", text_key="v2")
    await pq_repo.create(db_session, text="hidden", text_key="h2", hidden=True)
    await db_session.flush()
    rows = await pq_repo.all_with_agency(db_session)
    assert {r.text for r in rows} == {"visible", "hidden"}


async def test_update_and_delete(db_session):
    pq = await pq_repo.create(db_session, text="Q1", text_key="q3")
    await pq_repo.update(db_session, pq, {"text": "Q1 edited"})
    assert pq.text == "Q1 edited"
    await pq_repo.delete(db_session, pq)
    await db_session.flush()
    assert await pq_repo.text_key_exists(db_session, "q3") is False


async def test_bulk_create_ignore_conflicts(db_session):
    import uuid
    shared_id = uuid.uuid4()
    rows = [
        {"id": shared_id, "text": "a", "text_key": "bk1"},
        {"id": shared_id, "text": "b", "text_key": "bk2"},
    ]
    await pq_repo.bulk_create(db_session, rows, ignore_conflicts=True)
    all_rows = await pq_repo.all_with_agency(db_session)
    assert len(all_rows) == 1
