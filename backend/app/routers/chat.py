"""AI Chat router.

`POST /chat` is one handler: JSON by default, SSE when `stream=true`, driven
by the shared `prepare_turn`/`run_turn` pipeline. `model` selects the OneChat
version via `resolve_model_version`.
"""

import asyncio
import json
import time
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse, StreamingResponse
from opentelemetry import trace
from opentelemetry.trace import StatusCode

from app.auth.dependencies import get_current_user_optional
from app.auth.ws import resolve_ws_user, ws_origin_allowed
from app.config import settings
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services.chat.aggregate import collect_turn
from app.services.chat.model import resolve_model_version
from app.services.chat.stream import (
    ConversationNotFound,
    _stream_version,  # kept for test import compatibility
    prepare_turn,
    run_turn,
)
from app.services.chat.ws import ConnectionRegistry, handle_chat_frame
from app.utils import generate_uuid

router = APIRouter(prefix="/chat", tags=["Chat"])
tracer = trace.get_tracer(__name__)


@router.post("", summary="Send a query; JSON by default, SSE when stream=true")
async def chat(
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    user: User | None = Depends(get_current_user_optional),
) -> Any:
    query = body.query.strip()
    conversation_id = body.conversation_id or str(generate_uuid())
    version = resolve_model_version(body.model)

    with tracer.start_as_current_span("chat_endpoint") as span:
        span.set_attribute("conversation_id", conversation_id)
        span.set_attribute("stream", body.stream)
        span.set_attribute("chat_version", version)
        if not query:
            span.set_status(StatusCode.ERROR, "Missing query")
            raise HTTPException(status_code=400, detail="Missing query")

        try:
            plan = await prepare_turn(
                query=query, conversation_id=conversation_id, user=user,
                is_continuation=bool(body.conversation_id), requested_version=version,
            )
        except ConversationNotFound:
            span.set_status(StatusCode.ERROR, "Conversation not found")
            raise HTTPException(status_code=404, detail="Conversation not found")

        if plan.cached is not None:
            span.set_attribute("cache_hit", True)

        if body.stream:
            async def sse():
                async for event in run_turn(plan, background_tasks=background_tasks):
                    if event.name == "error":
                        span.set_status(StatusCode.ERROR, event.data.get("message"))
                    yield _sse_event(event.name, event.data)

            return StreamingResponse(
                sse(), media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        result = await collect_turn(plan, background_tasks=background_tasks)
        if result.error is not None:
            span.set_status(StatusCode.ERROR, result.error.get("message"))
            return JSONResponse(content={
                "success": False,
                "error": result.error.get("message"),
                "conversation_id": conversation_id,
                "responseTime": result.total_ms,
            })

        return {
            "success": True,
            "data": {
                "message_id": result.message_id,
                "cached": result.cached,
                "agentSteps": result.agent_steps,
                **result.answer_data,
            },
            "conversation_id": conversation_id,
            "responseTime": result.total_ms,
        }


def _sse_event(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ─── WebSocket mode ───────────────────────────────────────────────────────────

_connections = ConnectionRegistry()


@router.websocket("")
async def chat_ws(websocket: WebSocket) -> None:
    if not ws_origin_allowed(websocket):
        await websocket.close(code=1008)
        return
    if not _connections.acquire():
        await websocket.close(code=1013)  # try again later
        return

    async def send(frame: dict) -> None:
        await websocket.send_text(json.dumps(frame, ensure_ascii=False))

    try:
        await websocket.accept()
        user = await resolve_ws_user(websocket)
        deadline = time.monotonic() + settings.CHAT_WS_MAX_DURATION_SECONDS
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                await websocket.close(code=1000)
                return
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=remaining)
            except asyncio.TimeoutError:
                await websocket.close(code=1000)
                return
            websocket._raise_on_disconnect(message)
            await handle_chat_frame(message.get("text"), user, send)
    except WebSocketDisconnect:
        return
    finally:
        _connections.release()
