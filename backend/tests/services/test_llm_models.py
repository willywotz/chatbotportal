import pytest
from sqlalchemy.exc import IntegrityError

from app.models import LlmProvider, LlmRoute

pytestmark = pytest.mark.asyncio


async def test_provider_and_route_create_with_fk(db_session):
    p = LlmProvider(name="openrouter", base_url="https://x/v1/chat/completions",
                     api_key="k", auth_header="Authorization", auth_scheme="Bearer",
                     timeout_seconds=60.0, request_usage=True)
    db_session.add(p)
    await db_session.flush()
    r = LlmRoute(purpose="classification", provider_id=p.id, model="m1")
    db_session.add(r)
    await db_session.flush()

    assert r.purpose == "classification"
    await db_session.refresh(r, attribute_names=["provider"])
    assert r.provider.name == "openrouter"
    assert p.max_queue_size == 50 and p.enabled is True
    assert p.rate_limit_rps is None and p.rate_limit_rpm is None


async def test_purpose_is_unique(db_session):
    p = LlmProvider(name="p", base_url="u", api_key="k")
    db_session.add(p)
    await db_session.flush()
    db_session.add(LlmRoute(purpose="brief", provider_id=p.id, model="m"))
    await db_session.flush()

    db_session.add(LlmRoute(purpose="brief", provider_id=p.id, model="m2"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
