import pytest
from sqlalchemy import select

from app.features.llm.models.llm_provider import LlmProvider
from app.features.llm.models.llm_route import LlmRoute
from app.features.llm.services.seed import seed_llm_defaults

pytestmark = pytest.mark.asyncio


async def test_seed_creates_defaults_and_is_idempotent(db_session):
    await seed_llm_defaults(db_session)

    providers = (await db_session.execute(select(LlmProvider))).scalars().all()
    assert {p.name for p in providers} == {"openrouter", "thaillm"}

    routes = (await db_session.execute(select(LlmRoute))).scalars().all()
    assert {r.purpose for r in routes} == {
        "classification", "brief", "judge", "parse_spec", "popular_questions",
    }

    # editing then re-seeding must NOT overwrite
    openrouter = next(p for p in providers if p.name == "openrouter")
    openrouter.base_url = "https://edited"
    await db_session.flush()

    await seed_llm_defaults(db_session)

    refreshed = (await db_session.execute(
        select(LlmProvider).where(LlmProvider.name == "openrouter")
    )).scalar_one()
    assert refreshed.base_url == "https://edited"
    routes_after = (await db_session.execute(select(LlmRoute))).scalars().all()
    assert len(routes_after) == 5
