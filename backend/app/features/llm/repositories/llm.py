from __future__ import annotations

from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.llm.models.llm_binding import LlmBinding
from app.features.llm.models.llm_provider import LlmProvider


async def list_providers(session: AsyncSession) -> list[LlmProvider]:
    return list((await session.execute(select(LlmProvider))).scalars().all())


async def create_provider(session: AsyncSession, **fields) -> LlmProvider:
    obj = LlmProvider(**fields)
    session.add(obj)
    await session.flush()
    return obj


async def get_provider(session: AsyncSession, provider_id) -> LlmProvider | None:
    return await session.get(LlmProvider, provider_id)


async def get_provider_by_name(session: AsyncSession, name: str) -> LlmProvider | None:
    stmt = select(LlmProvider).where(LlmProvider.name == name)
    return (await session.execute(stmt)).scalars().first()


async def update_provider(session: AsyncSession, obj: LlmProvider, data: dict) -> LlmProvider:
    for key, value in data.items():
        setattr(obj, key, value)
    await session.flush()
    return obj


async def delete_provider(session: AsyncSession, provider: LlmProvider) -> None:
    await session.delete(provider)


async def provider_has_bindings(session: AsyncSession, provider_id) -> bool:
    stmt = select(literal(True)).where(LlmBinding.provider_id == provider_id).limit(1)
    return (await session.execute(stmt)).scalar() is not None


async def list_bindings(session: AsyncSession) -> list[LlmBinding]:
    return list((await session.execute(select(LlmBinding))).scalars().all())


async def create_binding(session: AsyncSession, **fields) -> LlmBinding:
    obj = LlmBinding(**fields)
    session.add(obj)
    await session.flush()
    return obj


async def get_binding(session: AsyncSession, binding_id) -> LlmBinding | None:
    return await session.get(LlmBinding, binding_id)


async def get_binding_by_purpose(session: AsyncSession, purpose: str) -> LlmBinding | None:
    stmt = select(LlmBinding).where(LlmBinding.purpose == purpose)
    return (await session.execute(stmt)).scalars().first()


async def enabled_binding_for_purpose(session: AsyncSession, purpose: str) -> LlmBinding | None:
    stmt = select(LlmBinding).where(
        LlmBinding.purpose == purpose, LlmBinding.enabled.is_(True)).limit(1)
    return (await session.execute(stmt)).scalars().first()


async def binding_purpose_exists(session: AsyncSession, purpose: str, *, exclude_id=None) -> bool:
    stmt = select(literal(True)).where(LlmBinding.purpose == purpose)
    if exclude_id is not None:
        stmt = stmt.where(LlmBinding.id != exclude_id)
    return (await session.execute(stmt.limit(1))).scalar() is not None


async def update_binding(session: AsyncSession, obj: LlmBinding, data: dict) -> LlmBinding:
    for key, value in data.items():
        setattr(obj, key, value)
    await session.flush()
    return obj


async def delete_binding(session: AsyncSession, binding: LlmBinding) -> None:
    await session.delete(binding)
