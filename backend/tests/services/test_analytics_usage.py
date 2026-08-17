"""Tests for app.services.analytics.usage — service-level home of usage_summary."""
from app.models import LlmUsage
from app.services.analytics.usage import usage_summary


async def test_usage_groups_by_purpose(db):
    await LlmUsage.create(model="m", purpose="router", prompt_tokens=10, completion_tokens=2, cost_usd=0.01)
    await LlmUsage.create(model="m", purpose="router", prompt_tokens=5, completion_tokens=1, cost_usd=0.02)
    await LlmUsage.create(model="m", purpose="synthesis", prompt_tokens=7, completion_tokens=3, cost_usd=0.005)

    rows = await usage_summary(group_by="purpose")

    by_key = {r["key"]: r for r in rows}
    assert by_key["router"]["prompt_tokens"] == 15
    assert by_key["router"]["cost_usd"] == 0.03
