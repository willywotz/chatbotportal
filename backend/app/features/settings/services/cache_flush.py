"""Similarity-cache invalidation via a stored flush timestamp.

find_similar_question ignores any cached Q/A created before the last flush.
"""
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.settings.repositories import setting as setting_repo
from app.core.utils import now

_KEY = "SIMILARITY_CACHE_FLUSHED_AT"


async def flush_similarity_cache(session: AsyncSession) -> None:
    await setting_repo.upsert(
        session, _KEY, now().isoformat(), updated_by="system", group="Cache", field_type="str",
    )


async def effective_cutoff(session: AsyncSession, window_cutoff: datetime) -> datetime:
    row = await setting_repo.get(session, _KEY)
    if row is None:
        return window_cutoff
    flushed_at = datetime.fromisoformat(row.value)
    return max(window_cutoff, flushed_at)
