from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.setting import Setting
from app.repositories import setting as setting_repo


async def fetch_db_settings(session: AsyncSession) -> dict[str, Setting]:
    rows = await setting_repo.all(session)
    return {r.key: r for r in rows}


async def upsert_setting(
    session: AsyncSession, key: str, value: str, updated_by: str, group: str, field_type: str,
) -> None:
    await setting_repo.upsert(
        session, key, value, updated_by=updated_by, group=group, field_type=field_type,
    )
