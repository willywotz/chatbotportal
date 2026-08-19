from app.repositories import llm_usage as llm_usage_repo


async def test_create_usage_row(db_session):
    row = await llm_usage_repo.create(
        db_session, model="google/gemini-2.5-flash-lite", purpose="classification",
        prompt_tokens=120, completion_tokens=8, cost_usd=0.000034,
    )
    assert row.total_tokens == 128


async def test_usage_row_stores_api_key_id(db_session):
    from uuid import uuid4
    kid = uuid4()
    row = await llm_usage_repo.create(
        db_session, model="m", purpose="classification",
        prompt_tokens=1, completion_tokens=1, api_key_id=kid,
    )
    assert row.api_key_id == kid
