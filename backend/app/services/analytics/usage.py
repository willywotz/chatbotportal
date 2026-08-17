"""LLM token/cost usage grouped by purpose, model, user, or API key."""

from __future__ import annotations

from datetime import datetime, timezone

from tortoise.functions import Sum

from app.models import LlmUsage
from app.models.user import User, UserAPIKey

_GROUP_FIELDS = {"purpose": "purpose", "model": "model", "user": "user_id", "api_key": "api_key_id"}


async def _enrich_api_keys(rows: list[dict]) -> list[dict]:
    ids = [r["key"] for r in rows if r["key"] is not None]
    keys = await UserAPIKey.filter(id__in=ids) if ids else []
    users = await User.filter(id__in={k.user_id for k in keys}) if keys else []
    email_by_user = {str(u.id): u.email for u in users}
    meta = {str(k.id): (k.name, k.key_prefix, email_by_user.get(str(k.user_id))) for k in keys}

    enriched: list[dict] = []
    bucket: dict | None = None
    for r in rows:
        info = meta.get(r["key"]) if r["key"] is not None else None
        if info is not None:
            r["name"], r["key_prefix"], r["owner_email"] = info
            enriched.append(r)
            continue
        if bucket is None:
            bucket = {
                "key": "—", "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0,
                "name": "web/session", "key_prefix": "—", "owner_email": None,
            }
            enriched.append(bucket)
        bucket["prompt_tokens"] += r["prompt_tokens"]
        bucket["completion_tokens"] += r["completion_tokens"]
        bucket["cost_usd"] = round(bucket["cost_usd"] + r["cost_usd"], 6)
    return enriched


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
    if group_by == "api_key":
        result = await _enrich_api_keys(result)
    return result
