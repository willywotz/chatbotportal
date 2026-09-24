import pytest

from app.features.llm.repositories import llm as llm_repo
from app.features.llm.services import rate_limit, resolve


@pytest.fixture(autouse=True)
def _reset_llm_caches():
    resolve.invalidate()
    rate_limit.reset_cache()
    yield
    resolve.invalidate()
    rate_limit.reset_cache()


@pytest.fixture
def make_binding(db_session):
    async def _make(purpose, *, kind="openai", model="m"):
        provider = await llm_repo.create_provider(
            db_session, name=f"prov-{purpose}", provider=kind, model=model, api_key="k")
        return await llm_repo.create_binding(
            db_session, purpose=purpose, provider_id=provider.id)
    return _make


@pytest.fixture
def set_fallback(db_session):
    async def _set(binding, fallback):
        await llm_repo.update_binding(
            db_session, binding, {"fallback_binding_id": fallback.id})
    return _set
