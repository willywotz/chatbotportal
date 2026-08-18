from __future__ import annotations

from tortoise.expressions import F

from app.models.agency import Agency


async def by_id(agency_id) -> Agency | None:
    return await Agency.get_or_none(id=agency_id)


async def list_and_count(*, status, connection_type, search_text) -> tuple[list[Agency], int]:
    qs = Agency.all()
    if status != "all":
        qs = qs.filter(status=status)
    if connection_type:
        qs = qs.filter(connection_type=connection_type.upper())
    if search_text:
        qs = qs.filter(name__icontains=search_text)
    return await qs, await qs.count()


async def create(**fields) -> Agency:
    return await Agency.create(**fields)


async def save(agency: Agency, *, update_fields: list[str] | None = None) -> None:
    await agency.save(update_fields=update_fields)


async def delete(agency: Agency) -> None:
    await agency.delete()


async def increment_calls(agency: Agency) -> Agency:
    """Atomically add one to total_calls, then refresh the readable value.

    A read-modify-write loses concurrent increments; the atomic SQL update is
    race-safe (matches the Go original).
    """
    await Agency.filter(id=agency.id).update(total_calls=F("total_calls") + 1)
    await agency.refresh_from_db(fields=["total_calls"])
    return agency


async def count_all() -> int:
    return await Agency.all().count()
