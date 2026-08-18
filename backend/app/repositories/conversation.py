from __future__ import annotations

from app.models.conversation import Conversation


async def by_id(conversation_id, *, exclude_deleted: bool = False) -> Conversation | None:
    filters: dict = {"id": conversation_id}
    if exclude_deleted:
        filters["deleted_at"] = None
    return await Conversation.get_or_none(**filters)


async def list_and_count(
    *, user_id, title_contains: str | None, agency_contains: str | None,
    created_from, created_to, offset: int | None, limit: int | None,
) -> tuple[list[Conversation], int]:
    qs = Conversation.filter(deleted_at=None)
    if user_id is not None:
        qs = qs.filter(user_id=user_id)
    if title_contains:
        qs = qs.filter(title__icontains=title_contains)
    if agency_contains:
        # JSONB containment (Postgres). Not supported on the SQLite test DB,
        # so this branch is covered only in a Postgres-backed environment.
        qs = qs.filter(agencies__contains=agency_contains)
    if created_from is not None:
        qs = qs.filter(created_at__gte=created_from)
    if created_to is not None:
        qs = qs.filter(created_at__lt=created_to)
    total = await qs.count()
    page_qs = qs.order_by("-created_at")
    if limit is not None:
        page_qs = page_qs.offset(offset or 0).limit(limit)
    return await page_qs, total


async def create(**fields) -> Conversation:
    return await Conversation.create(**fields)


async def save(conv: Conversation, *, update_fields: list[str] | None = None) -> None:
    await conv.save(update_fields=update_fields)


async def delete(conv: Conversation) -> None:
    await conv.delete()
