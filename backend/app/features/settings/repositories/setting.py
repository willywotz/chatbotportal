from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import SECRET_FIELD_NAMES
from app.features.settings.models.setting import Setting


async def all(session: AsyncSession) -> list[Setting]:
    return list((await session.execute(select(Setting))).scalars().all())


async def get(session: AsyncSession, key: str) -> Setting | None:
    return await session.get(Setting, key)


async def upsert(
    session: AsyncSession, key: str, value: str, *, updated_by: str, group: str, field_type: str,
) -> Setting:
    obj = await session.get(Setting, key)
    if obj is None:
        obj = Setting(key=key)
        session.add(obj)
    obj.value = value
    obj.updated_by = updated_by
    obj.is_secret = key in SECRET_FIELD_NAMES
    obj.group = group
    obj.field_type = field_type
    await session.flush()
    return obj
