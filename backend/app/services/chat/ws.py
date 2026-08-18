"""Transport-free WebSocket logic for /chat.

The router hands raw frame text in and a `send` callable out, so the whole
protocol is unit-testable without a real socket. One turn runs to completion
before the next frame is read, so exactly one response is ever in flight.
"""
import json
import logging
from typing import Awaitable, Callable

from app.config import settings
from app.models.user import User
from app.services.chat.model import resolve_model_version
from app.services.chat.stream import ConversationNotFound, prepare_turn, run_turn
from app.utils import generate_uuid

logger = logging.getLogger(__name__)

Send = Callable[[dict], Awaitable[None]]


class ConnectionRegistry:
    """Caps concurrent sockets; reads the setting live so tests can mutate it."""

    def __init__(self) -> None:
        self._open = 0

    def acquire(self) -> bool:
        if self._open >= settings.CHAT_WS_MAX_CONNECTIONS:
            return False
        self._open += 1
        return True

    def release(self) -> None:
        self._open = max(0, self._open - 1)


def _error(message: str, code: int = 400) -> dict:
    return {"event": "error", "data": {"message": message, "code": code}}


async def handle_chat_frame(raw: str | None, user: User | None, send: Send) -> None:
    if raw is None:
        await send(_error("This endpoint accepts text frames only."))
        return
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, RecursionError):
        await send(_error("Frame is not valid JSON."))
        return
    if not isinstance(payload, dict) or not str(payload.get("query", "")).strip():
        await send(_error("Frame must be a JSON object with a non-empty `query`."))
        return

    query = str(payload["query"]).strip()
    conversation_id = payload.get("conversation_id") or str(generate_uuid())
    version = resolve_model_version(payload.get("model"))
    try:
        plan = await prepare_turn(
            query=query, conversation_id=conversation_id, user=user,
            is_continuation=bool(payload.get("conversation_id")), requested_version=version,
        )
    except ConversationNotFound:
        await send(_error("Conversation not found", code=404))
        return

    async for event in run_turn(plan, schedule=None):
        await send({"event": event.name, "data": event.data})
