import logging
from datetime import timedelta

from tortoise import Tortoise

from app.config import settings
from app.models.connection_log import ConnectionLog
from app.models.conversation import Message
from app.services.cache_flush import effective_cutoff
from app.utils import now

logger = logging.getLogger(__name__)


async def find_similar_question(
    query: str,
) -> tuple[Message, Message, ConnectionLog] | None:
    """Find a similar prior question within SIMILARITY_WINDOW_SECONDS via pg_trgm.

    Returns (user_message, assistant_message, connection_log) if a match above
    threshold exists in a successful conversation, else None. Never raises —
    DB/extension errors degrade to a cache miss.
    """
    if not settings.SIMILARITY_CACHE_ENABLED:
        return None

    threshold = settings.SIMILARITY_THRESHOLD
    cutoff = await effective_cutoff(now() - timedelta(seconds=settings.SIMILARITY_WINDOW_SECONDS))

    match = await _similarity_search(query, threshold, cutoff)
    if match is None:
        return None

    answer = await _fetch_answer_by_match(match)
    if answer is None:
        return None

    assistant_msg, conn_log = answer
    return (match, assistant_msg, conn_log)


async def _fetch_answer_by_match(
    match: Message,
) -> tuple[Message, ConnectionLog] | None:
    """Fetch the assistant message and connection log for a matched user message.

    Uses a single join query that simultaneously verifies the conversation
    status is 'success', reducing the original 3-query tail to one round trip.
    """
    conn = Tortoise.get_connection("default")
    is_postgres = conn.capabilities.dialect == "postgres"
    if is_postgres:
        # Postgres uses numbered placeholders; $1 is reused for conversation_id.
        sql = """
        SELECT m.id AS asst_id, cl.id AS cl_id
        FROM messages m
        JOIN conversations c ON c.id = $1 AND c.status = 'success'
        JOIN connection_logs cl ON cl.assistant_message_id = m.id
        WHERE m.parent_id = $2
          AND m.role = 'assistant'
          AND m.conversation_id = $1
        LIMIT 1
        """
        params = [str(match.conversation_id), str(match.id)]
    else:
        # SQLite uses positional ? placeholders; repeat the conversation_id value.
        sql = """
        SELECT m.id AS asst_id, cl.id AS cl_id
        FROM messages m
        JOIN conversations c ON c.id = ? AND c.status = 'success'
        JOIN connection_logs cl ON cl.assistant_message_id = m.id
        WHERE m.parent_id = ?
          AND m.role = 'assistant'
          AND m.conversation_id = ?
        LIMIT 1
        """
        params = [str(match.conversation_id), str(match.id), str(match.conversation_id)]
    rows = await conn.execute_query_dict(sql, params)
    if not rows:
        logger.debug(
            "No cached answer found for message %s (no assistant or non-success conv)", match.id
        )
        return None

    row = rows[0]
    try:
        asst_msg = await Message.get(id=row["asst_id"])
        cl = await ConnectionLog.get(id=row["cl_id"])
    except Exception:
        logger.warning("Failed to fetch assistant/conn_log for match %s", match.id)
        return None
    return (asst_msg, cl)


async def _similarity_search(
    query: str,
    threshold: float,
    cutoff,
) -> Message | None:
    conn = Tortoise.get_connection("default")
    try:
        rows = await conn.execute_query_dict(
            """
            SELECT id, content, conversation_id, similarity(content, $1) AS sim_score
            FROM messages
            WHERE role = 'user'
              AND created_at >= $2
              AND similarity(content, $3) >= $4
            ORDER BY similarity(content, $5) DESC
            LIMIT 1
            """,
            [query, cutoff, query, threshold, query],
        )
    except Exception:
        logger.warning("pg_trgm similarity search unavailable — extension not installed?")
        return None

    if not rows:
        return None

    row = rows[0]
    return await Message.get(id=row["id"])
