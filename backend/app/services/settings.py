"""
Data access for admin-editable runtime settings, backed by the `settings` table.
"""

from __future__ import annotations

from app.config import SECRET_FIELD_NAMES
from app.models.setting import Setting


async def fetch_db_settings() -> dict[str, Setting]:
    rows = await Setting.all()
    return {r.key: r for r in rows}


async def upsert_setting(key: str, value: str, updated_by: str, group: str, field_type: str) -> None:
    await Setting.update_or_create(
        key=key,
        defaults={
            "value": value,
            "updated_by": updated_by,
            "is_secret": key in SECRET_FIELD_NAMES,
            "group": group,
            "field_type": field_type,
        },
    )
