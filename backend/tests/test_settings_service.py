"""Tests for app.services.settings — data access moved out of the router."""
import pytest
from sqlalchemy import select

from app.models.setting import Setting
from app.services import settings as settings_service

pytestmark = pytest.mark.asyncio


async def test_fetch_db_settings_keys_by_setting_key(db_session):
    db_session.add(Setting(key="A", value="1", group="App", field_type="int"))
    await db_session.flush()
    db_map = await settings_service.fetch_db_settings(db_session)
    assert db_map["A"].value == "1"


async def test_upsert_setting_creates_row(db_session):
    await settings_service.upsert_setting(db_session, "B", "true", "admin@x.com", "App", "bool")
    row = await db_session.get(Setting, "B")
    assert row.value == "true"
    assert row.updated_by == "admin@x.com"
    assert row.group == "App"
    assert row.field_type == "bool"
    assert row.is_secret is False


async def test_upsert_setting_marks_secret_fields(db_session):
    await settings_service.upsert_setting(db_session, "OPENROUTER_API_KEY", "sk-1", "a@x.com", "LLM", "str")
    row = await db_session.get(Setting, "OPENROUTER_API_KEY")
    assert row.is_secret is True


async def test_upsert_setting_updates_existing_row(db_session):
    db_session.add(Setting(key="C", value="old", group="App", field_type="str"))
    await db_session.flush()
    await settings_service.upsert_setting(db_session, "C", "new", "a@x.com", "App", "str")
    rows = (await db_session.execute(select(Setting).where(Setting.key == "C"))).scalars().all()
    assert len(rows) == 1
    assert rows[0].value == "new"
