import pytest

from app.features.llm.services import resolve
from app.features.llm.services.errors import LlmError


@pytest.mark.asyncio
async def test_no_binding_is_config_error(db_session):
    resolve.invalidate()
    with pytest.raises(LlmError) as e:
        await resolve.for_purpose(db_session, "brief")
    assert e.value.kind == "config"


@pytest.mark.asyncio
async def test_resolves_enabled_binding(db_session, make_binding):
    await make_binding("judge", model="a")
    resolve.invalidate()
    r = await resolve.for_purpose(db_session, "judge")
    assert r.model == "a"
    assert r.kind == "openai"
    assert r.headers == {}


@pytest.mark.asyncio
async def test_resolves_custom_headers_as_dict(db_session):
    from app.features.llm.repositories import llm as llm_repo
    provider = await llm_repo.create_provider(
        db_session, name="p-hdr", provider="openai", model="m", api_key="k",
        headers=[{"name": "X-Title", "value": "portal"},
                 {"name": "HTTP-Referer", "value": "https://x"}])
    await llm_repo.create_binding(db_session, purpose="brief", provider_id=provider.id)
    resolve.invalidate()
    r = await resolve.for_purpose(db_session, "brief")
    assert r.headers == {"X-Title": "portal", "HTTP-Referer": "https://x"}


@pytest.mark.asyncio
async def test_disabled_provider_is_config_error(db_session, make_binding):
    from app.features.llm.repositories import llm as llm_repo
    binding = await make_binding("judge", model="a")
    provider = await llm_repo.get_provider(db_session, binding.provider_id)
    await llm_repo.update_provider(db_session, provider, {"enabled": False})
    resolve.invalidate()
    with pytest.raises(LlmError) as e:
        await resolve.for_purpose(db_session, "judge")
    assert e.value.kind == "config"
