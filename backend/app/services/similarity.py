import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.connection_log import ConnectionLog
from app.models.conversation import Message
from app.repositories import similarity as similarity_repo
from app.services.cache_flush import effective_cutoff
from app.utils import now

logger = logging.getLogger(__name__)


async def find_similar_question(
    session: AsyncSession, query: str,
) -> tuple[Message, Message, ConnectionLog] | None:
    """Find a similar prior question within SIMILARITY_WINDOW_SECONDS via PGroonga.

    Returns (user_message, assistant_message, connection_log) if a match above
    the score floor exists in a successful conversation, else None. Never raises —
    DB/extension errors degrade to a cache miss.
    """
    if not settings.SIMILARITY_CACHE_ENABLED:
        return None

    cutoff = await effective_cutoff(session, now() - timedelta(seconds=settings.SIMILARITY_WINDOW_SECONDS))
    # withinlazy: PGroonga score floor needs tuning; tokenizer/normalizer (NormalizerNFKC150) is the knob
    score_floor = settings.SIMILARITY_THRESHOLD if settings.SIMILARITY_THRESHOLD > 0 else None

    try:
        match = await similarity_repo.find_similar(session, query, cutoff, score_floor=score_floor)
    except Exception:
        logger.warning("PGroonga similarity search unavailable — extension not installed?")
        return None
    if match is None:
        return None

    answer = await similarity_repo.answer_for(session, match)
    if answer is None:
        return None

    assistant_msg, conn_log = answer
    return (match, assistant_msg, conn_log)
