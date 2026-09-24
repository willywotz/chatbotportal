import pytest

from app.features.llm.repositories import llm as llm_repo


@pytest.fixture
def make_binding(db_session):
    async def _make(purpose, *, kind="openai", model="m"):
        provider = await llm_repo.create_provider(
            db_session, name=f"prov-{purpose}", provider=kind, model=model, api_key="k")
        return await llm_repo.create_binding(
            db_session, purpose=purpose, provider_id=provider.id)
    return _make
