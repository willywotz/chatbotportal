"""LLM token/cost usage grouped by purpose, model, or user."""

from __future__ import annotations

from datetime import datetime, timezone

from tortoise.functions import Sum

from app.models import LlmUsage

_GROUP_FIELDS = {"purpose": "purpose", "model": "model", "user": "user_id"}


async def usage_summary(group_by: str = "purpose", date_from: datetime | None = None,
                        date_to: datetime | None = None) -> list[dict]:
    field = _GROUP_FIELDS.get(group_by, "purpose")
    if date_from is not None and date_from.tzinfo is None:
        date_from = date_from.replace(tzinfo=timezone.utc)
    if date_to is not None and date_to.tzinfo is None:
        date_to = date_to.replace(tzinfo=timezone.utc)
    qs = LlmUsage.all()
    if date_from is not None:
        qs = qs.filter(created_at__gte=date_from)
    if date_to is not None:
        qs = qs.filter(created_at__lt=date_to)
    rows = (
        await qs
        .annotate(prompt=Sum("prompt_tokens"), completion=Sum("completion_tokens"), cost=Sum("cost_usd"))
        .group_by(field)
        .values(field, "prompt", "completion", "cost")
    )
    result = [
        {
            "key": str(r[field]) if r[field] is not None else None,
            "prompt_tokens": r["prompt"] or 0,
            "completion_tokens": r["completion"] or 0,
            "cost_usd": round(r["cost"] or 0.0, 6),
        }
        for r in rows
    ]
    return result
