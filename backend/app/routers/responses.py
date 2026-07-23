"""OpenAI-compatible Responses API.

    POST /api/v1/responses    stream=false → a complete Response object
                              stream=true  → OpenAI SSE
    WS   /api/v1/responses    response.create frames in, the same events out

All three transports drive one `run_response()` generator, so their wire output
cannot drift. Errors use OpenAI's envelope (services/responses/errors.py), not
the portal's.
"""
import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from opentelemetry import trace

from app.auth.dependencies import _resolve_token, get_current_user_optional
from app.models.user import User
from app.schemas.responses import ResponsesRequest
from app.services.chat.stream import ConversationNotFound, prepare_turn, run_turn
from app.config import settings
from app.services.openai.identity import owner_or_ephemeral
from app.services.responses.continuity import resolve_conversation, response_id_for
from app.services.responses.errors import ResponsesApiError
from app.services.responses.request import extract_query, resolve_model
from app.services.responses.session import WsSession, _error_frame
from app.services.responses.translate import ResponseAccumulator

router = APIRouter(prefix="/responses", tags=["Responses"])
tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)


async def run_response(
    request: ResponsesRequest,
    *,
    user: User | None,
    background_tasks: BackgroundTasks | None,
    cache: dict[str, str] | None = None,
) -> AsyncIterator[dict]:
    """Drive one turn and yield OpenAI Responses events.

    Shared by every transport. `cache` is a WebSocket connection's local
    response-id → conversation-id map; None on HTTP.
    """
    model, stream_version = resolve_model(request.model)
    query = extract_query(request.input)
    conversation_id, is_continuation = await resolve_conversation(
        previous_response_id=request.previous_response_id,
        conversation=request.conversation,
        cache=cache,
    )

    try:
        plan = await prepare_turn(
            query=query, conversation_id=conversation_id, user=user,
            is_continuation=is_continuation,
        )
    except ConversationNotFound:
        raise ResponsesApiError(
            f"Conversation '{conversation_id}' not found",
            param="conversation", code="conversation_not_found", status=404,
        )

    # A model id that pins a version wins over CHAT_STREAM_VERSION.
    if plan.stream_version != stream_version:
        plan.stream_version = stream_version
        plan.upstream_url = (
            settings.ONECHAT_V4_URL if stream_version == "v4" else settings.ONECHAT_V5_URL
        )

    accumulator = ResponseAccumulator(
        response_id=response_id_for(plan.assistant_message_id),
        model=model,
        conversation_id=conversation_id,
        cached=plan.cached is not None,
        stream_version=plan.stream_version,
    )
    yield accumulator.created_event()

    async for chat_event in run_turn(plan, background_tasks=background_tasks):
        for event in accumulator.consume(chat_event):
            yield event

    if cache is not None:
        cache[accumulator.response_id] = conversation_id


@router.post("", summary="Create a model response (OpenAI Responses API compatible)")
async def create_response(
    body: ResponsesRequest,
    background_tasks: BackgroundTasks,
    user: User | None = Depends(get_current_user_optional),
) -> Any:
    with tracer.start_as_current_span("responses_endpoint") as span:
        span.set_attribute("stream", body.stream)
        owner, session_token = await owner_or_ephemeral(user)

        if body.stream:
            events = run_response(body, user=owner, background_tasks=background_tasks)
            # Prime the generator now, while we're still inside this handler and
            # any ResponsesApiError from the prelude (resolve_model,
            # resolve_conversation, prepare_turn) is caught by the
            # normal exception handler. StreamingResponse commits HTTP 200 and
            # headers before its body iterator's first __anext__(), so priming
            # after construction would raise once the response has already
            # started — see run_response()'s docstring for the same hazard.
            first_event = await events.__anext__()

            async def sse() -> AsyncIterator[str]:
                def render(event: dict) -> str:
                    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

                yield render(first_event)
                async for event in events:
                    yield render(event)
                yield "data: [DONE]\n\n"

            resp = StreamingResponse(
                sse(), media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
            if session_token:
                resp.headers["X-Portal-Session"] = session_token
            return resp

        final = None
        async for event in run_response(body, user=owner, background_tasks=background_tasks):
            if event["type"] in ("response.completed", "response.failed"):
                final = event["response"]
        if final is None:
            raise ResponsesApiError(
                "The upstream produced no answer.", type="server_error",
                code="no_answer", status=502,
            )
        resp = JSONResponse(content=final)
        if session_token:
            resp.headers["X-Portal-Session"] = session_token
        return resp


# ─── WebSocket mode ───────────────────────────────────────────────────────────


class _ConnectionRegistry:
    """Caps concurrent sockets.

    An endpoint that allows anonymous callers and holds hour-long connections is
    otherwise an unbounded resource sink.
    """

    def __init__(self) -> None:
        self._open = 0

    def acquire(self) -> bool:
        if self._open >= settings.RESPONSES_WS_MAX_CONNECTIONS:
            return False
        self._open += 1
        return True

    def release(self) -> None:
        self._open = max(0, self._open - 1)


_connections = _ConnectionRegistry()


async def _ws_user(websocket) -> User | None:
    """Resolve the caller from the Authorization header; anonymous on anything else.

    Browsers cannot set headers on a WebSocket — browser clients should use the
    SSE transport. There is deliberately no query-parameter token fallback: it
    would leak API keys into access logs.
    """
    header = websocket.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    try:
        return await _resolve_token(header[7:])
    except Exception:
        return None


@router.websocket("")
async def responses_websocket(websocket: WebSocket) -> None:
    if not _connections.acquire():
        await websocket.close(code=1013)  # try again later
        return

    async def send(frame: dict) -> None:
        await websocket.send_text(json.dumps(frame, ensure_ascii=False))

    try:
        await websocket.accept()
        session = WsSession(user=await _ws_user(websocket))
        deadline = time.monotonic() + settings.RESPONSES_WS_MAX_DURATION_SECONDS
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                await send(_connection_limit_frame())
                await websocket.close(code=1000)
                return
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=remaining)
            except asyncio.TimeoutError:
                await send(_connection_limit_frame())
                await websocket.close(code=1000)
                return
            websocket._raise_on_disconnect(message)
            raw = message.get("text")
            if raw is None:
                # A binary frame — e.g. Go/JS clients that always send bytes.
                # Reject it as bad input rather than assuming/decoding UTF-8,
                # so the wire contract stays "JSON text frames only".
                await send(_error_frame(ResponsesApiError(
                    "This endpoint accepts text frames only; binary frames are"
                    " not supported.",
                )))
                continue
            # Awaited before the next receive: one response in flight at a time,
            # additional frames queue in the socket buffer. No multiplexing.
            await session.handle_text(raw, send)
    except WebSocketDisconnect:
        return
    finally:
        _connections.release()


def _connection_limit_frame() -> dict:
    return {
        "type": "error",
        **ResponsesApiError(
            f"Responses websocket connection limit reached ({settings.RESPONSES_WS_MAX_DURATION_SECONDS} seconds). "
            "Create a new websocket connection to continue.",
            type="invalid_request_error",
            code="websocket_connection_limit_reached",
        ).envelope(),
    }
