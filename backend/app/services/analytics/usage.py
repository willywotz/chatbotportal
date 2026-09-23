"""LLM token/cost usage grouped by purpose, model, or user."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import analytics as analytics_repo

_GROUP_FIELDS = {"purpose": "purpose", "model": "model", "user": "user_id"}


async def usage_summary(session: AsyncSession, group_by: str = "purpose", date_from: datetime | None = None,
                        date_to: datetime | None = None) -> list[dict]:
    field = _GROUP_FIELDS.get(group_by, "purpose")
    if date_from is not None and date_from.tzinfo is None:
        date_from = date_from.replace(tzinfo=timezone.utc)
    if date_to is not None and date_to.tzinfo is None:
        date_to = date_to.replace(tzinfo=timezone.utc)

    rows = await analytics_repo.llm_usage_summary(session, group_by, date_from, date_to)
    return [
        {
            "key": str(r[field]) if r[field] is not None else None,
            "prompt_tokens": r["prompt"] or 0,
            "completion_tokens": r["completion"] or 0,
            "cost_usd": round(r["cost"] or 0.0, 6),
        }
        for r in rows
    ]
