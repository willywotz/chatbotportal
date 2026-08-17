"""Tests for app.services.settings — data access moved out of the router."""

from app.models.setting import Setting
from app.services import settings as settings_service


async def test_fetch_db_settings_keys_by_setting_key(db):
    await Setting.create(key="A", value="1", group="App", field_type="int")
    db_map = await settings_service.fetch_db_settings()
    assert db_map["A"].value == "1"


async def test_upsert_setting_creates_row(db):
    await settings_service.upsert_setting("B", "true", "admin@x.com", "App", "bool")
    row = await Setting.get(key="B")
    assert row.value == "true"
    assert row.updated_by == "admin@x.com"
    assert row.group == "App"
    assert row.field_type == "bool"
    assert row.is_secret is False


async def test_upsert_setting_marks_secret_fields(db):
    await settings_service.upsert_setting("OPENROUTER_API_KEY", "sk-1", "a@x.com", "LLM", "str")
    row = await Setting.get(key="OPENROUTER_API_KEY")
    assert row.is_secret is True


async def test_upsert_setting_updates_existing_row(db):
    await Setting.create(key="C", value="old", group="App", field_type="str")
    await settings_service.upsert_setting("C", "new", "a@x.com", "App", "str")
    assert await Setting.filter(key="C").count() == 1
    row = await Setting.get(key="C")
    assert row.value == "new"
