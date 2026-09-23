import pytest

from app.features.settings.repositories import setting as setting_repo

pytestmark = pytest.mark.asyncio


async def test_upsert_creates_then_updates(db_session):
    await setting_repo.upsert(
        db_session, "SOME_KEY", "v1", updated_by="admin", group="general", field_type="str")
    row = await setting_repo.get(db_session, "SOME_KEY")
    assert row.value == "v1"

    await setting_repo.upsert(
        db_session, "SOME_KEY", "v2", updated_by="admin2", group="general", field_type="str")
    row = await setting_repo.get(db_session, "SOME_KEY")
    assert row.value == "v2"
    assert row.updated_by == "admin2"


async def test_upsert_marks_secret_fields(db_session):
    await setting_repo.upsert(
        db_session, "OPENROUTER_API_KEY", "secret", updated_by="admin",
        group="llm", field_type="str")
    row = await setting_repo.get(db_session, "OPENROUTER_API_KEY")
    assert row.is_secret is True


async def test_all(db_session):
    await setting_repo.upsert(db_session, "K1", "v", updated_by="a", group="g", field_type="str")
    await setting_repo.upsert(db_session, "K2", "v", updated_by="a", group="g", field_type="str")
    rows = await setting_repo.all(db_session)
    assert {r.key for r in rows} == {"K1", "K2"}
    assert await setting_repo.get(db_session, "missing") is None
