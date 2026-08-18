from app.models import LlmUsage
from app.routers.insight import usage_summary


async def test_usage_groups_by_purpose(db):
    await LlmUsage.create(model="m", purpose="router", prompt_tokens=10, completion_tokens=2, cost_usd=0.01)
    await LlmUsage.create(model="m", purpose="router", prompt_tokens=5, completion_tokens=1, cost_usd=0.02)
    await LlmUsage.create(model="m", purpose="synthesis", prompt_tokens=7, completion_tokens=3, cost_usd=0.005)

    rows = await usage_summary(group_by="purpose")

    by_key = {r["key"]: r for r in rows}
    assert by_key["router"]["prompt_tokens"] == 15
    assert by_key["router"]["cost_usd"] == 0.03


async def test_usage_groups_by_user(db):
    from uuid import uuid4
    user_a, user_b = uuid4(), uuid4()
    await LlmUsage.create(model="m", purpose="router", prompt_tokens=10, completion_tokens=2,
                          cost_usd=0.01, user_id=user_a)
    await LlmUsage.create(model="m", purpose="router", prompt_tokens=5, completion_tokens=1,
                          cost_usd=0.02, user_id=user_b)

    rows = await usage_summary(group_by="user")
    by_key = {r["key"]: r for r in rows}

    assert by_key[str(user_a)]["prompt_tokens"] == 10
    assert by_key[str(user_b)]["prompt_tokens"] == 5


async def test_usage_unknown_group_by_falls_back_to_purpose(db):
    """API-key attribution is gone (API keys are removed); an unrecognized
    group_by (including the old "api_key") falls back to grouping by purpose,
    with no key-metadata enrichment."""
    await LlmUsage.create(model="m", purpose="router", prompt_tokens=10, completion_tokens=2, cost_usd=0.01)

    rows = await usage_summary(group_by="api_key")
    by_key = {r["key"]: r for r in rows}

    assert by_key["router"]["prompt_tokens"] == 10
    assert "name" not in by_key["router"]


async def test_usage_date_filter(db):
    from datetime import datetime, timezone
    old = await LlmUsage.create(model="m", purpose="router", prompt_tokens=1, completion_tokens=0)
    await LlmUsage.filter(id=old.id).update(created_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    await LlmUsage.create(model="m", purpose="router", prompt_tokens=9, completion_tokens=0)

    rows = await usage_summary(group_by="purpose", date_from=datetime(2021, 1, 1, tzinfo=timezone.utc))
    by_key = {r["key"]: r for r in rows}
    assert by_key["router"]["prompt_tokens"] == 9


async def test_usage_date_filter_naive_treated_as_utc(db):
    from datetime import datetime, timezone
    old = await LlmUsage.create(model="m", purpose="router", prompt_tokens=1, completion_tokens=0)
    await LlmUsage.filter(id=old.id).update(created_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    await LlmUsage.create(model="m", purpose="router", prompt_tokens=9, completion_tokens=0)

    # naive datetime (no tzinfo) must be treated as UTC, not rejected or mishandled
    rows = await usage_summary(group_by="purpose", date_from=datetime(2021, 1, 1))
    by_key = {r["key"]: r for r in rows}
    assert by_key["router"]["prompt_tokens"] == 9
