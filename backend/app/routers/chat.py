"""
AI Chat router.

Public endpoints (schema-visible)
----------------------------------
  POST /chat            → canonical sync endpoint (delegates to /chat/external)
  POST /chat/stream     → OneChat v4 (SSE proxy)

Internal endpoints (hidden from OpenAPI schema, still functional)
-----------------------------------------------------------------
  POST /chat/external   → OneChat v3 sync (alias of /chat; deprecated)
"""

import json
import logging
import time
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from opentelemetry import trace
from opentelemetry.trace import StatusCode
from tortoise.exceptions import DoesNotExist

from app.auth.dependencies import get_current_user_optional
from app.config import settings
from app.models.connection_log import ConnectionLog
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat.llm import classify_message_category
from app.services.chat.stream import (
    ConversationNotFound,
    _stream_upstream,  # re-exported: tests/routers/test_chat_stream_version.py imports it from here
    prepare_turn,
    run_turn,
)
from app.services.chat.turn import save_turn
from app.services.similarity import find_similar_question
from app.services.log_sanitize import sanitize_body
from app.services.session import ensure_session_warmed
from app.utils import generate_uuid

router = APIRouter(prefix="/chat", tags=["Chat"])
tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)


# ─── External endpoint (OneChat v3) ────────────────────────────────────────────

@router.post("/external", include_in_schema=False, deprecated=True)  # alias; use POST /chat
async def chat_external(body: ChatRequest, background_tasks: BackgroundTasks, user: User | None = Depends(get_current_user_optional)) -> ChatResponse:
    with tracer.start_as_current_span("chat_external_endpoint") as span:
        query = body.query.strip()
        conversation_id = body.conversation_id or str(generate_uuid())

        if body.conversation_id:
            try:
                conv = await Conversation.get(id=conversation_id)
            except DoesNotExist:
                raise HTTPException(status_code=404, detail="Conversation not found")

        if not query:
            span.set_status(StatusCode.ERROR, "Missing query")
            raise HTTPException(status_code=400, detail="Missing query")

        if not body.conversation_id:
            cached = await find_similar_question(query=query)
            if cached:
                user_msg, asst_msg, _ = cached
                span.set_attribute("cache_hit", True)
                new_asst_msg = await _copy_cached_answer(
                    query=query,
                    conversation_id=conversation_id,
                    user=user,
                    user_msg=user_msg,
                    asst_msg=asst_msg,
                )
                return {
                    "success": True,
                    "data": {
                        "message_id": new_asst_msg.id,
                        "answer": asst_msg.content,
                        "references": asst_msg.sources if asst_msg.sources else [],
                        "agentSteps": asst_msg.agent_steps if asst_msg.agent_steps else [],
                        "agencies": [],
                        "confidence": settings.SIMILARITY_THRESHOLD,
                        "cached": True,
                    },
                    "conversation_id": conversation_id,
                    "responseTime": 0,
                }
        else:
            try:
                await ensure_session_warmed(conv, settings.MCP_ENDPOINT_URL)
            except Exception:
                logger.warning("Session warm-up failed for conversation %s", conversation_id)

        payload = {"query": query, "mcp_endpoint_url": settings.MCP_ENDPOINT_URL, "session_id": conversation_id}

        async with httpx.AsyncClient(timeout=settings.EXTERNAL_CHAT_TIMEOUT) as client:
            start_time_ns = time.perf_counter_ns()
            resp = await client.post(settings.ONECHAT_V3_URL, headers={"Content-Type": "application/json"}, json=payload)
            end_time_ns = time.perf_counter_ns()

        if resp.status_code != 200:
            span.set_status(StatusCode.ERROR, f"External chat request failed with status {resp.status_code}")
            raise HTTPException(status_code=502, detail="Failed to get response from external chat service")

        response_time = int((end_time_ns - start_time_ns) // 1_000_000)
        raw_data = resp.json()
        span.set_attributes({"external_response": resp.text})

        data = raw_data.get("data", {})
        answer = data.get("answer", "").strip()
        errors = data.get("errors", [])

        agency_ids = []
        if "data" in raw_data and "sections" in raw_data["data"]:
            for sec in raw_data["data"]["sections"]:
                if "agencies" in sec:
                    agency_ids.extend([ag["id"] for ag in sec["agencies"]])

        saved = await save_turn(
            query=query, conversation_id=conversation_id, answer=answer,
            references=data.get("references", []), category=None,
            agency_ids=agency_ids, response_time=response_time, user=user,
            succeeded=bool(answer), external_session_id=data.get("session_id"),
            errors=errors,
        )

        # Create ConnectionLog after save_turn so message IDs are available (enables v3 cache).
        # The logged detail/bodies are the raw upstream values, unchanged.
        await ConnectionLog.create(
            id=str(generate_uuid()),
            action="query",
            connection_type="external_chat",
            status="success" if answer else "error",
            latency_ms=response_time,
            detail=sanitize_body(f"Query: {query}\n\nAnswer: {raw_data}"),
            request_body=sanitize_body(json.dumps(payload)),
            response_body=sanitize_body(json.dumps(raw_data)),
            message_id=saved.user_message_id,
            assistant_message_id=saved.assistant_message_id,
        )

        background_tasks.add_task(classify_message_category, saved.user_message_id, query, answer)

        return {
            "success": True,
            "data": {
                "message_id": saved.assistant_message_id,
                "answer": answer,
                "references": data.get("references", []),
                "agentSteps": data.get("agentSteps", []),
                "agencies": data.get("agencies", []),
                "confidence": data.get("confidence", 0.0),
            },
            "conversation_id": conversation_id,
            "responseTime": response_time,
        }


# ─── Stream endpoint (OneChat v5 SSE) ─────────────────────────────────────────

@router.post("/stream", summary="Send a query and receive SSE streaming response")
async def chat_stream(body: ChatRequest, request: Request, background_tasks: BackgroundTasks, user: User | None = Depends(get_current_user_optional)):
    """Format the shared turn pipeline as SSE. All logic lives in services/chat/stream.py."""
    query = body.query.strip()
    conversation_id = body.conversation_id or str(generate_uuid())

    with tracer.start_as_current_span("chat_stream_endpoint") as span:
        span.set_attribute("conversation_id", conversation_id)
        if not query:
            span.set_status(StatusCode.ERROR, "Missing query")
            raise HTTPException(status_code=400, detail="Missing query")
        span.set_attribute("query", query)

        try:
            plan = await prepare_turn(
                query=query, conversation_id=conversation_id, user=user,
                is_continuation=bool(body.conversation_id),
            )
        except ConversationNotFound:
            span.set_status(StatusCode.ERROR, "Conversation not found for session warm-up")
            raise HTTPException(status_code=404, detail="Conversation not found")

        span.set_attribute("chat_stream_version", plan.stream_version)
        if plan.cached is not None:
            span.set_attribute("cache_hit", True)

        async def sse():
            async for event in run_turn(plan, background_tasks=background_tasks):
                if event.name == "error":
                    span.set_status(StatusCode.ERROR, event.data.get("message"))
                yield _sse_event(event.name, event.data)

        return StreamingResponse(
            sse(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )


# ─── Default route (delegates to /external) ───────────────────────────────────

@router.post("", summary="Send a query and get a synthesised AI response")
async def chat(body: ChatRequest, background_tasks: BackgroundTasks, user: User | None = Depends(get_current_user_optional)) -> ChatResponse:
    with tracer.start_as_current_span("chat_endpoint"):
        return await chat_external(body, background_tasks, user)


# ─── HTTP helpers ─────────────────────────────────────────────────────────────

def _sse_event(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _parse_sse_block(block: str) -> tuple[str, Any] | None:
    event_name = "message"
    data_line = None
    for line in block.strip().split("\n"):
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_line = line[5:].strip()
    if not data_line:
        return None
    try:
        return event_name, json.loads(data_line)
    except json.JSONDecodeError:
        return None


async def _copy_cached_answer(
    *,
    query: str,
    conversation_id: str,
    user: User | None,
    user_msg: Message,
    asst_msg: Message,
) -> Message:
    """Copy a cached answer into a fresh message owned by `conversation_id`.

    Copies are intentionally NOT cache sources: no ConnectionLog is created,
    so `_fetch_answer_by_match` (which inner-joins connection_logs in
    find_similar_question) will never resurface a copy.
    """
    try:
        conv = await Conversation.get(id=conversation_id)
        conv.message_count += 2  # 1 user + 1 assistant message per turn
        await conv.save()
    except Exception:
        await Conversation.create(
            id=conversation_id,
            title=query[:settings.TITLE_MAX_LENGTH],
            preview=query[:settings.PREVIEW_MAX_LENGTH],
            agencies=[],
            status="success",
            message_count=2,  # 1 user + 1 assistant message per turn
            response_time=0,
            user_id=user.id if user else None,
        )

    new_user_msg = await Message.create(
        conversation_id=conversation_id,
        role="user",
        content=query,
        category=user_msg.category,
    )
    return await Message.create(
        parent_id=new_user_msg.id,
        conversation_id=conversation_id,
        role="assistant",
        content=asst_msg.content,
        sources=asst_msg.sources,
        agent_steps=asst_msg.agent_steps,
        agency_ids=asst_msg.agency_ids,
        response_time=0,
    )
