"""Single transactional writer for a chat turn (conversation + 2 messages)."""
import uuid
from dataclasses import dataclass

from tortoise.exceptions import DoesNotExist
from tortoise.transactions import in_transaction

from app.config import settings
from app.models.conversation import Conversation, Message
from app.utils import generate_uuid, now


@dataclass
class SavedTurn:
    user_message_id: str
    assistant_message_id: str
    conversation_id: str


async def save_turn(
    *,
    query: str,
    conversation_id: str,
    answer: str,
    references: list,
    category: str | None,
    agency_ids: list[str],
    response_time: int,
    user,
    succeeded: bool,
    external_session_id: str | None = None,
    errors: list | None = None,
    summary: str | None = None,
    summary_references: list | None = None,
    agent_steps: dict | list | None = None,
    title: str | None = None,
    assistant_message_id: uuid.UUID | None = None,
) -> SavedTurn:
    """Create/extend a conversation and write the user+assistant messages atomically.

    `succeeded=False` records the conversation as status="failed" so it never
    seeds the similarity cache (find_similar_question filters status="success").
    `title` overrides the query-derived conversation title, but only when the
    conversation is created (the first turn) — see the v5 `thread_name` rule.
    `summary`/`summary_references` are the v5 executive summary and its
    citations; both stay empty in v4 mode and on the v5 degrade path.
    `assistant_message_id` pre-allocates the assistant row's primary key so a
    streaming transport can name the response before the turn is persisted.
    """
    status = "success" if succeeded else "failed"
    async with in_transaction():
        try:
            conv = await Conversation.get(id=conversation_id)
            conv.message_count += 2
            conv.updated_at = now()
            if not succeeded:
                # One-way ratchet: once "failed", status is never restored to "success",
                # keeping the conversation out of the similarity cache on recovery.
                conv.status = "failed"
            await conv.save()
        except DoesNotExist:
            conv = await Conversation.create(
                id=conversation_id,
                title=(title or query)[: settings.TITLE_MAX_LENGTH],
                preview=query[: settings.PREVIEW_MAX_LENGTH],
                agencies=[],
                status=status,
                message_count=2,
                response_time=response_time,
                user_id=user.id if user else None,
                external_session_id=external_session_id,
            )
        user_msg = await Message.create(
            conversation_id=conversation_id, role="user", content=query, category=category,
        )
        asst_msg = await Message.create(
            id=assistant_message_id or generate_uuid(),
            parent_id=user_msg.id,
            conversation_id=conversation_id,
            role="assistant",
            content=answer,
            sources=references,
            response_time=response_time,
            agency_ids=agency_ids,
            errors=errors or [],
            summary=summary,
            summary_references=summary_references or [],
            agent_steps=agent_steps if agent_steps is not None else [],
        )
    return SavedTurn(str(user_msg.id), str(asst_msg.id), conversation_id)
