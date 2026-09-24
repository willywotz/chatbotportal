import pytest
from sqlalchemy import select

from app.features.llm.models.llm_provider import LlmProvider
from app.features.llm.models.llm_binding import LlmBinding
from app.features.llm.services.seed import seed_llm_defaults

pytestmark = pytest.mark.asyncio


async def test_seed_creates_openai_provider_and_bindings(db_session):
    await seed_llm_defaults(db_session)

    providers = (await db_session.execute(select(LlmProvider))).scalars().all()
    assert len(providers) == 1
    assert providers[0].provider == "openai"

    bindings = (await db_session.execute(select(LlmBinding))).scalars().all()
    assert {b.purpose for b in bindings} == {
        "classification", "brief", "judge", "parse_spec", "popular_questions",
    }
    assert all(b.enabled for b in bindings)


async def test_seed_is_idempotent(db_session):
    await seed_llm_defaults(db_session)
    provider = (await db_session.execute(select(LlmProvider))).scalar_one()
    provider.base_url = "https://edited"
    await db_session.flush()

    await seed_llm_defaults(db_session)

    refreshed = (await db_session.execute(select(LlmProvider))).scalar_one()
    assert refreshed.base_url == "https://edited"
    bindings = (await db_session.execute(select(LlmBinding))).scalars().all()
    assert len(bindings) == 5
