from datetime import timedelta

import pytest

from app.services.cache_flush import effective_cutoff, flush_similarity_cache
from app.utils import now

pytestmark = pytest.mark.asyncio


async def test_flush_moves_cutoff_forward(db_session):
    window_cutoff = now() - timedelta(days=3)
    assert await effective_cutoff(db_session, window_cutoff) == window_cutoff

    await flush_similarity_cache(db_session)

    cutoff = await effective_cutoff(db_session, window_cutoff)
    assert cutoff > window_cutoff
