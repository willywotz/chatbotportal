from datetime import datetime, timezone

from app.features.llm.repositories import llm_usage as llm_usage_repo
from app.features.analytics.routers.insight import usage_summary


async def test_usage_groups_by_purpose(db_session):
    await llm_usage_repo.create(db_session, model="m", purpose="router", prompt_tokens=10, completion_tokens=2, cost_usd=0.01)
    await llm_usage_repo.create(db_session, model="m", purpose="router", prompt_tokens=5, completion_tokens=1, cost_usd=0.02)
    await llm_usage_repo.create(db_session, model="m", purpose="synthesis", prompt_tokens=7, completion_tokens=3, cost_usd=0.005)

    rows = await usage_summary(db_session, group_by="purpose")

    by_key = {r["key"]: r for r in rows}
    assert by_key["router"]["prompt_tokens"] == 15
    assert by_key["router"]["cost_usd"] == 0.03


async def test_usage_groups_by_user(db_session):
    from uuid import uuid4
    user_a, user_b = uuid4(), uuid4()
    await llm_usage_repo.create(db_session, model="m", purpose="router", prompt_tokens=10, completion_tokens=2,
                                cost_usd=0.01, user_id=user_a)
    await llm_usage_repo.create(db_session, model="m", purpose="router", prompt_tokens=5, completion_tokens=1,
                                cost_usd=0.02, user_id=user_b)

    rows = await usage_summary(db_session, group_by="user")
    by_key = {r["key"]: r for r in rows}

    assert by_key[str(user_a)]["prompt_tokens"] == 10
    assert by_key[str(user_b)]["prompt_tokens"] == 5


async def test_usage_unknown_group_by_falls_back_to_purpose(db_session):
    """API-key attribution is gone (API keys are removed); an unrecognized
    group_by (including the old "api_key") falls back to grouping by purpose,
    with no key-metadata enrichment."""
    await llm_usage_repo.create(db_session, model="m", purpose="router", prompt_tokens=10, completion_tokens=2, cost_usd=0.01)

    rows = await usage_summary(db_session, group_by="api_key")
    by_key = {r["key"]: r for r in rows}

    assert by_key["router"]["prompt_tokens"] == 10
    assert "name" not in by_key["router"]


async def test_usage_date_filter(db_session):
    old = await llm_usage_repo.create(db_session, model="m", purpose="router", prompt_tokens=1, completion_tokens=0)
    old.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    await db_session.flush()
    await llm_usage_repo.create(db_session, model="m", purpose="router", prompt_tokens=9, completion_tokens=0)

    rows = await usage_summary(db_session, group_by="purpose", date_from=datetime(2021, 1, 1, tzinfo=timezone.utc))
    by_key = {r["key"]: r for r in rows}
    assert by_key["router"]["prompt_tokens"] == 9


async def test_usage_date_filter_naive_treated_as_utc(db_session):
    old = await llm_usage_repo.create(db_session, model="m", purpose="router", prompt_tokens=1, completion_tokens=0)
    old.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    await db_session.flush()
    await llm_usage_repo.create(db_session, model="m", purpose="router", prompt_tokens=9, completion_tokens=0)

    # naive datetime (no tzinfo) must be treated as UTC, not rejected or mishandled
    rows = await usage_summary(db_session, group_by="purpose", date_from=datetime(2021, 1, 1))
    by_key = {r["key"]: r for r in rows}
    assert by_key["router"]["prompt_tokens"] == 9
