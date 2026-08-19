import pytest

from app.repositories import llm as llm_repo
from app.services.llm import client as c

pytestmark = pytest.mark.asyncio


async def test_resolve_returns_provider_and_model(db_session):
    c.invalidate()
    p = await llm_repo.create_provider(
        db_session, name="openrouter", base_url="u", api_key="k",
        auth_header="Authorization", auth_scheme="Bearer",
        timeout_seconds=12.0, request_usage=True,
    )
    await llm_repo.create_route(db_session, purpose="classification", provider_id=p.id, model="m1")
    r = await c._resolve(db_session, "classification")
    assert r.model == "m1" and r.base_url == "u" and r.timeout == 12.0
    assert r.auth_header == "Authorization" and r.request_usage is True


async def test_resolve_missing_route_raises_config(db_session):
    c.invalidate()
    with pytest.raises(c.LlmError) as e:
        await c._resolve(db_session, "nope")
    assert e.value.kind == "config"


async def test_route_timeout_override_wins(db_session):
    c.invalidate()
    p = await llm_repo.create_provider(db_session, name="p", base_url="u", api_key="k", timeout_seconds=60.0)
    await llm_repo.create_route(db_session, purpose="brief", provider_id=p.id, model="m", timeout_override=99.0)
    assert (await c._resolve(db_session, "brief")).timeout == 99.0
