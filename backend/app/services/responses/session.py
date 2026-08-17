"""Per-connection WebSocket logic for the Responses API, without the socket.

The transport passes raw text in and a `send` callable out, so the whole
protocol is testable by direct call. Sequencing is by construction: the router
awaits `handle_text` before reading the next frame, so exactly one response is
ever in flight and additional `response.create` frames queue in the socket
buffer — which is what "no multiplexing" means upstream.
"""
import json
import logging
from typing import Awaitable, Callable

from pydantic import ValidationError

from app.config import settings
from app.models.user import User
from app.schemas.responses import ResponsesRequest
from app.services.responses.continuity import resolve_conversation
from app.services.responses.errors import ResponsesApiError
from app.services.session import ensure_session_warmed

logger = logging.getLogger(__name__)

Send = Callable[[dict], Awaitable[None]]


class WsSession:

    def __init__(self, user: User | None):
        self.user = user
        # response id → conversation id for this connection, mirroring OpenAI's
        # connection-local cache. A miss falls back to the database.
        self.cache: dict[str, str] = {}

    async def handle_text(self, raw: str, send: Send) -> None:
        try:
            # RecursionError guards against pathologically nested JSON, which
            # the C decoder accepts past the point of blowing the C stack.
            payload = json.loads(raw)
        except (json.JSONDecodeError, RecursionError):
            await send(_error_frame(ResponsesApiError("Frame is not valid JSON.")))
            return

        if not isinstance(payload, dict) or payload.get("type") != "response.create":
            await send(_error_frame(ResponsesApiError(
                "Unsupported frame type; this endpoint accepts `response.create` only.",
                param="type",
            )))
            return

        try:
            request = ResponsesRequest.model_validate(payload)
        except ValidationError as e:
            await send(_error_frame(ResponsesApiError(str(e))))
            return

        try:
            if not request.generate:
                await self._warm(request)
                return
            await self._generate(request, send)
        except ResponsesApiError as e:
            await send(_error_frame(e))
        except Exception:
            logger.exception("Unhandled error generating a response")
            await send(_error_frame(ResponsesApiError(
                "An unexpected error occurred.", type="server_error", status=500,
            )))

    async def _warm(self, request: ResponsesRequest) -> None:
        """`generate: false` — resolve and warm the session, emit nothing."""
        from app.models.conversation import Conversation

        conversation_id, is_continuation = await resolve_conversation(
            previous_response_id=request.previous_response_id,
            conversation=request.conversation,
            cache=self.cache,
        )
        if not is_continuation:
            return
        conv = await Conversation.filter(id=conversation_id).first()
        if conv is None:
            raise ResponsesApiError(
                f"Conversation '{conversation_id}' not found",
                param="conversation", code="conversation_not_found", status=404,
            )
        try:
            await ensure_session_warmed(conv, settings.MCP_ENDPOINT_URL)
        except Exception:
            logger.warning("Warm-up failed for conversation %s", conversation_id)

    async def _generate(self, request: ResponsesRequest, send: Send) -> None:
        from app.routers.responses import run_response

        async for event in run_response(
            request, user=self.user, background_tasks=None, cache=self.cache,
        ):
            await send(event)


def _error_frame(error: ResponsesApiError) -> dict:
    return {"type": "error", **error.envelope()}
