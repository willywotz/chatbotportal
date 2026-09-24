import pytest
from sqlalchemy import inspect
from app.features.llm.models.llm_provider import LlmProvider  # noqa: F401
from app.features.llm.models.llm_binding import LlmBinding    # noqa: F401


@pytest.mark.asyncio
async def test_tables_exist_after_upgrade(_engine):
    async with _engine.connect() as conn:
        names = await conn.run_sync(lambda c: inspect(c).get_table_names())
    assert {"llm_provider", "llm_binding", "llm_usage"} <= set(names)
    assert "llm_routes" not in names and "llm_providers" not in names
