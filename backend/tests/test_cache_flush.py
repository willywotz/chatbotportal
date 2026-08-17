from datetime import timedelta

from app.services.cache_flush import effective_cutoff, flush_similarity_cache
from app.utils import now


async def test_flush_moves_cutoff_forward(db):
    window_cutoff = now() - timedelta(days=3)
    assert await effective_cutoff(window_cutoff) == window_cutoff

    await flush_similarity_cache()

    cutoff = await effective_cutoff(window_cutoff)
    assert cutoff > window_cutoff
