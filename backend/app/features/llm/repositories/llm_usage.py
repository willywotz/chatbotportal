from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.llm.models.llm_usage import LlmUsage


async def create(session: AsyncSession, **fields) -> LlmUsage:
    obj = LlmUsage(**fields)
    session.add(obj)
    await session.flush()
    return obj
