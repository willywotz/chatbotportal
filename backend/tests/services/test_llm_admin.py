"""Unit tests for the LLM provider/route admin CRUD service.

Router-level behavior (status codes, masking, cache invalidation) stays
covered by tests/routers/test_llm_admin.py; these tests exercise the ORM
access moved out of the router.
"""
import uuid

import pytest

from app.errors import ApiError
from app.repositories import llm as llm_repo
from app.services.llm import admin as llm_admin

pytestmark = pytest.mark.asyncio


async def test_create_provider_persists(db_session):
    provider = await llm_admin.create_provider(db_session, {"name": "p1", "base_url": "https://p1.example"})
    assert await llm_repo.get_provider(db_session, provider.id) is not None


async def test_list_providers_returns_all(db_session):
    await llm_repo.create_provider(db_session, name="p1", base_url="https://p1.example")
    await llm_repo.create_provider(db_session, name="p2", base_url="https://p2.example")
    assert len(await llm_admin.list_providers(db_session)) == 2


async def test_get_provider_not_found_raises_404(db_session):
    with pytest.raises(ApiError) as exc:
        await llm_admin.get_provider(db_session, uuid.uuid4())
    assert exc.value.status == 404


async def test_update_provider_applies_fields(db_session):
    provider = await llm_repo.create_provider(db_session, name="p1", base_url="https://p1.example", api_key="k")
    updated = await llm_admin.update_provider(db_session, provider.id, {"timeout_seconds": 30.0})
    assert updated.timeout_seconds == 30.0
    assert updated.api_key == "k"  # untouched field stays


async def test_delete_provider_removes_it(db_session):
    provider = await llm_repo.create_provider(db_session, name="p1", base_url="https://p1.example")
    await llm_admin.delete_provider(db_session, provider.id)
    await db_session.flush()
    assert await llm_repo.get_provider(db_session, provider.id) is None


async def test_delete_provider_in_use_raises_409(db_session):
    provider = await llm_repo.create_provider(db_session, name="p1", base_url="https://p1.example")
    await llm_repo.create_route(db_session, purpose="judge", provider_id=provider.id, model="m")
    with pytest.raises(ApiError) as exc:
        await llm_admin.delete_provider(db_session, provider.id)
    assert exc.value.status == 409
    assert await llm_repo.get_provider(db_session, provider.id) is not None


async def test_create_route_unknown_provider_raises_404(db_session):
    with pytest.raises(ApiError) as exc:
        await llm_admin.create_route(db_session, {"purpose": "brief", "provider_id": uuid.uuid4(), "model": "m"})
    assert exc.value.status == 404


async def test_create_route_duplicate_purpose_raises_409(db_session):
    provider = await llm_repo.create_provider(db_session, name="p1", base_url="https://p1.example")
    await llm_repo.create_route(db_session, purpose="brief", provider_id=provider.id, model="m")
    with pytest.raises(ApiError) as exc:
        await llm_admin.create_route(db_session, {"purpose": "brief", "provider_id": provider.id, "model": "m2"})
    assert exc.value.status == 409


async def test_update_route_new_provider_not_found_raises_404(db_session):
    provider = await llm_repo.create_provider(db_session, name="p1", base_url="https://p1.example")
    route = await llm_repo.create_route(db_session, purpose="brief", provider_id=provider.id, model="m")
    with pytest.raises(ApiError) as exc:
        await llm_admin.update_route(db_session, route.id, {"provider_id": uuid.uuid4()})
    assert exc.value.status == 404


async def test_update_route_duplicate_purpose_raises_409(db_session):
    provider = await llm_repo.create_provider(db_session, name="p1", base_url="https://p1.example")
    await llm_repo.create_route(db_session, purpose="brief", provider_id=provider.id, model="m")
    other = await llm_repo.create_route(db_session, purpose="judge", provider_id=provider.id, model="m")
    with pytest.raises(ApiError) as exc:
        await llm_admin.update_route(db_session, other.id, {"purpose": "brief"})
    assert exc.value.status == 409


async def test_delete_route_removes_it(db_session):
    provider = await llm_repo.create_provider(db_session, name="p1", base_url="https://p1.example")
    route = await llm_repo.create_route(db_session, purpose="brief", provider_id=provider.id, model="m")
    await llm_admin.delete_route(db_session, route.id)
    await db_session.flush()
    assert await llm_repo.get_route(db_session, route.id) is None


async def test_route_provider_name_resolves_fk(db_session):
    provider = await llm_repo.create_provider(db_session, name="p1", base_url="https://p1.example")
    route = await llm_repo.create_route(db_session, purpose="brief", provider_id=provider.id, model="m")
    assert await llm_admin.route_provider_name(db_session, route) == "p1"
