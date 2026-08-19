import uuid

import pytest

from app.repositories import llm as llm_repo

pytestmark = pytest.mark.asyncio


async def _provider(session, name="OpenRouter"):
    return await llm_repo.create_provider(session, name=name, base_url="https://x")


async def test_create_and_get_provider(db_session):
    p = await _provider(db_session)
    fetched = await llm_repo.get_provider(db_session, p.id)
    assert fetched.id == p.id
    assert await llm_repo.get_provider(db_session, uuid.uuid4()) is None


async def test_update_provider_setattr_loop(db_session):
    p = await _provider(db_session)
    updated = await llm_repo.update_provider(db_session, p, {"name": "Renamed"})
    assert updated.name == "Renamed"


async def test_provider_has_routes(db_session):
    p = await _provider(db_session)
    assert await llm_repo.provider_has_routes(db_session, p.id) is False
    await llm_repo.create_route(db_session, purpose="chat", provider_id=p.id, model="m1")
    assert await llm_repo.provider_has_routes(db_session, p.id) is True


async def test_route_purpose_exists(db_session):
    p = await _provider(db_session)
    assert await llm_repo.route_purpose_exists(db_session, "chat") is False
    await llm_repo.create_route(db_session, purpose="chat", provider_id=p.id, model="m1")
    assert await llm_repo.route_purpose_exists(db_session, "chat") is True
    assert await llm_repo.route_purpose_exists(db_session, "chat", exclude_id=None) is True
