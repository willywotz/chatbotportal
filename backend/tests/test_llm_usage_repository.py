import pytest
from sqlalchemy import select

from app.models.llm_usage import LlmUsage
from app.repositories import llm_usage as llm_usage_repo

pytestmark = pytest.mark.asyncio


async def test_create_persists_usage_row(db_session):
    row = await llm_usage_repo.create(
        db_session, model="m1", purpose="classification", prompt_tokens=3, completion_tokens=2,
    )
    fetched = (await db_session.execute(select(LlmUsage).where(LlmUsage.id == row.id))).scalars().one()
    assert fetched.model == "m1"
    assert fetched.purpose == "classification"
    assert fetched.total_tokens == 5
