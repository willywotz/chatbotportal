from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.connection_log import ConnectionLog
from app.features.chat.models.conversation import Message


async def find_similar(
    session: AsyncSession, query: str, cutoff: datetime, *, score_floor: float | None = None,
) -> Message | None:
    """Find the highest-scoring prior user message via PGroonga similar-search (`&@*`)."""
    sql = """
    SELECT id, pgroonga_score(tableoid, ctid) AS score
    FROM messages
    WHERE role = 'user'
      AND created_at >= :cutoff
      AND content &@* :query
    """
    params = {"cutoff": cutoff, "query": query}
    if score_floor is not None:
        sql += " AND pgroonga_score(tableoid, ctid) >= :score_floor"
        params["score_floor"] = score_floor
    sql += " ORDER BY score DESC LIMIT 1"

    row = (await session.execute(text(sql), params)).mappings().first()
    if not row:
        return None
    return await session.get(Message, row["id"])


async def answer_for(session: AsyncSession, match: Message) -> tuple[Message, ConnectionLog] | None:
    """Fetch the assistant reply and connection log for a matched user message.

    A single join verifies the conversation status is 'success' and locates the
    assistant message plus its connection log in one round trip.
    """
    sql = """
    SELECT m.id AS asst_id, cl.id AS cl_id
    FROM messages m
    JOIN conversations c ON c.id = :conversation_id AND c.status = 'success'
    JOIN connection_logs cl ON cl.assistant_message_id = m.id
    WHERE m.parent_id = :parent_id
      AND m.role = 'assistant'
      AND m.conversation_id = :conversation_id
    LIMIT 1
    """
    params = {"conversation_id": match.conversation_id, "parent_id": match.id}
    row = (await session.execute(text(sql), params)).mappings().first()
    if not row:
        return None

    asst_msg = await session.get(Message, row["asst_id"])
    conn_log = await session.get(ConnectionLog, row["cl_id"])
    if asst_msg is None or conn_log is None:
        return None
    return (asst_msg, conn_log)
