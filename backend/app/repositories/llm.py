from __future__ import annotations

from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_provider import LlmProvider
from app.models.llm_route import LlmRoute


async def list_providers(session: AsyncSession) -> list[LlmProvider]:
    return list((await session.execute(select(LlmProvider))).scalars().all())


async def create_provider(session: AsyncSession, **fields) -> LlmProvider:
    obj = LlmProvider(**fields)
    session.add(obj)
    await session.flush()
    return obj


async def get_provider(session: AsyncSession, provider_id) -> LlmProvider | None:
    return await session.get(LlmProvider, provider_id)


async def update_provider(session: AsyncSession, obj: LlmProvider, data: dict) -> LlmProvider:
    for key, value in data.items():
        setattr(obj, key, value)
    await session.flush()
    return obj


async def delete_provider(session: AsyncSession, provider: LlmProvider) -> None:
    await session.delete(provider)


async def provider_has_routes(session: AsyncSession, provider_id) -> bool:
    stmt = select(literal(True)).where(LlmRoute.provider_id == provider_id).limit(1)
    return (await session.execute(stmt)).scalar() is not None


async def list_routes(session: AsyncSession) -> list[LlmRoute]:
    return list((await session.execute(select(LlmRoute))).scalars().all())


async def route_purpose_exists(session: AsyncSession, purpose: str, *, exclude_id=None) -> bool:
    stmt = select(literal(True)).where(LlmRoute.purpose == purpose)
    if exclude_id is not None:
        stmt = stmt.where(LlmRoute.id != exclude_id)
    return (await session.execute(stmt.limit(1))).scalar() is not None


async def create_route(session: AsyncSession, **fields) -> LlmRoute:
    obj = LlmRoute(**fields)
    session.add(obj)
    await session.flush()
    return obj


async def get_route(session: AsyncSession, route_id) -> LlmRoute | None:
    return await session.get(LlmRoute, route_id)


async def update_route(session: AsyncSession, obj: LlmRoute, data: dict) -> LlmRoute:
    for key, value in data.items():
        setattr(obj, key, value)
    await session.flush()
    return obj


async def delete_route(session: AsyncSession, route: LlmRoute) -> None:
    await session.delete(route)
