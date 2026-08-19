from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agency import Agency


async def by_id(session: AsyncSession, agency_id) -> Agency | None:
    return await session.get(Agency, agency_id)


async def list_and_count(session: AsyncSession, *, status, connection_type, search_text):
    stmt = select(Agency).order_by(Agency.name)
    if status != "all":
        stmt = stmt.where(Agency.status == status)
    if connection_type:
        stmt = stmt.where(Agency.connection_type == connection_type.upper())
    if search_text:
        stmt = stmt.where(Agency.name.ilike(f"%{search_text}%"))
    rows = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    )).scalar_one()
    return list(rows), total


async def create(session: AsyncSession, **fields) -> Agency:
    obj = Agency(**fields)
    session.add(obj)
    await session.flush()
    return obj


async def save(session: AsyncSession, agency: Agency, *, update_fields=None) -> None:
    await session.flush()


async def delete(session: AsyncSession, agency: Agency) -> None:
    await session.delete(agency)


async def increment_calls(session: AsyncSession, agency: Agency) -> Agency:
    await session.execute(
        update(Agency).where(Agency.id == agency.id).values(total_calls=Agency.total_calls + 1)
    )
    await session.refresh(agency, attribute_names=["total_calls"])
    return agency


async def count_all(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(Agency))).scalar_one()


async def list_by_statuses(session: AsyncSession, statuses: list[str]) -> list[Agency]:
    stmt = select(Agency).where(Agency.status.in_(statuses))
    return list((await session.execute(stmt)).scalars().all())


async def by_ids(session: AsyncSession, ids) -> list[Agency]:
    stmt = select(Agency).where(Agency.id.in_(ids))
    return list((await session.execute(stmt)).scalars().all())


async def by_name(session: AsyncSession, name: str) -> Agency | None:
    stmt = select(Agency).where(Agency.name == name).limit(1)
    return (await session.execute(stmt)).scalars().first()


_MCP_COLUMNS = (
    "id", "name", "status", "description", "connection_type",
    "data_scope", "endpoint_url", "expected_payload", "api_headers",
)


async def list_for_mcp(session: AsyncSession) -> list[dict]:
    """Every agency, as plain dicts keyed for the MCP `list_agency` tool."""
    stmt = select(*(getattr(Agency, col) for col in _MCP_COLUMNS))
    rows = (await session.execute(stmt)).all()
    return [dict(zip(_MCP_COLUMNS, row)) for row in rows]
