"""Tests for app.features.analytics.services.usage — service-level home of usage_summary."""
from app.features.llm.models.llm_usage import LlmUsage
from app.features.analytics.services.usage import usage_summary


async def test_usage_groups_by_purpose(db_session):
    db_session.add_all([
        LlmUsage(model="m", purpose="router", prompt_tokens=10, completion_tokens=2, cost_usd=0.01),
        LlmUsage(model="m", purpose="router", prompt_tokens=5, completion_tokens=1, cost_usd=0.02),
        LlmUsage(model="m", purpose="synthesis", prompt_tokens=7, completion_tokens=3, cost_usd=0.005),
    ])
    await db_session.flush()

    rows = await usage_summary(db_session, group_by="purpose")

    by_key = {r["key"]: r for r in rows}
    assert by_key["router"]["prompt_tokens"] == 15
    assert by_key["router"]["cost_usd"] == 0.03
