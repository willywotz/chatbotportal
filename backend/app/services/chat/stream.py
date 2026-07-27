"""Transport-free chat-turn pipeline, shared by /chat and /responses.

Split in two on purpose. `prepare_turn()` does everything that must be able to
fail before any bytes are committed to the client — conversation lookup,
similarity-cache probe, session warm-up — so a transport can still return a
plain HTTP error. `run_turn()` is the generator: it streams the upstream,
persists the turn, and yields the terminal `done` event carrying the real
message id.
"""
import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, NamedTuple

from fastapi import BackgroundTasks
from opentelemetry import trace
from opentelemetry.trace import StatusCode
from tortoise.exceptions import DoesNotExist

from app.config import settings
from app.models.connection_log import ConnectionLog
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.services.chat.llm import classify_message_category
from app.services.chat.pipeline_snapshot import build_pipeline_snapshot
from app.services.chat.turn import save_turn
from app.services.log_sanitize import sanitize_body
from app.services.onechat import OneChatError, get_client, resolve_version
from app.services.session import ensure_session_warmed
from app.services.similarity import find_similar_question
from app.trace_util import with_trace_query
from app.utils import generate_uuid

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Tasks scheduled without a FastAPI BackgroundTasks (the WebSocket path) must be
# strongly referenced or the loop may collect them mid-flight.
_background_tasks: set[asyncio.Task] = set()


class ChatEvent(NamedTuple):
    """One OneChat pipeline event: the upstream vocabulary, unchanged."""

    name: str
    data: dict


class ConversationNotFound(Exception):
    """A continuation named a conversation that does not exist."""


@dataclass
class TurnPlan:
    query: str
    conversation_id: str
    user: User | None
    stream_version: str
    assistant_message_id: uuid.UUID
    cached: tuple[Message, Message, Any] | None = None


def _stream_version() -> str:
    """Streaming version resolver (kept for the chat.py re-export)."""
    return resolve_version()


async def prepare_turn(
    *, query: str, conversation_id: str, user: User | None, is_continuation: bool,
    requested_version: str | None = None,
) -> TurnPlan:
    """Resolve everything needed to run a turn, failing loudly if it cannot.

    Raises ConversationNotFound when `is_continuation` names an unknown id.
    """
    stream_version = resolve_version(requested_version)
    plan = TurnPlan(
        query=query,
        conversation_id=conversation_id,
        user=user,
        stream_version=stream_version,
        assistant_message_id=generate_uuid(),
    )

    if not is_continuation:
        plan.cached = await find_similar_question(query=query)
        return plan

    try:
        conv = await Conversation.get(id=conversation_id)
    except DoesNotExist:
        raise ConversationNotFound(conversation_id)
    try:
        await ensure_session_warmed(conv, settings.MCP_ENDPOINT_URL)
    except Exception:
        logger.warning("Session warm-up failed for conversation %s", conversation_id)
    return plan


async def run_turn(
    plan: TurnPlan, *, background_tasks: BackgroundTasks | None = None
) -> AsyncIterator[ChatEvent]:
    """Stream one turn to completion, persisting it before the terminal `done`."""
    if plan.cached is not None:
        async for event in _replay_cached(plan, background_tasks):
            yield event
        return
    async for event in _stream_live(plan, background_tasks):
        yield event


async def _replay_cached(
    plan: TurnPlan, background_tasks: BackgroundTasks | None
) -> AsyncIterator[ChatEvent]:
    user_msg, asst_msg, conn_log = plan.cached
    await asyncio.sleep(0.01)
    try:
        answer_data = json.loads(conn_log.response_body)
    except Exception:
        answer_data = {"answer": asst_msg.content}

    assistant_id = await _persist(
        plan, answer_data=answer_data, session_id=None,
        total_ms=0, latency_ms=0, thread_name=None,
        background_tasks=background_tasks, pipeline_events=[],
    )
    yield ChatEvent("answer", {
        "answer": asst_msg.content,
        "summary": answer_data.get("summary") or asst_msg.summary or "",
        "references": answer_data.get("references") or asst_msg.summary_references or [],
    })
    yield ChatEvent("done", {
        "session_id": plan.conversation_id, "total_ms": 0, "message_id": str(assistant_id),
    })


async def _stream_live(
    plan: TurnPlan, background_tasks: BackgroundTasks | None
) -> AsyncIterator[ChatEvent]:
    answer_data = None
    session_id = None
    total_ms = None
    done_event_data = None
    thread_name = None
    start_ns = time.perf_counter_ns()
    log_latency_ms = 0
    version = plan.stream_version
    pipeline_events: list[tuple[str, dict]] = []

    try:
        with tracer.start_as_current_span("onechat_call") as call_span:
            call_span.set_attribute("conversation_id", plan.conversation_id)
            call_span.set_attribute("chat_stream_version", version)
            mcp_url = with_trace_query(settings.MCP_ENDPOINT_URL)
            async for event_name, event_data in get_client(version).events(
                plan.query, mcp_url, plan.conversation_id
            ):
                if log_latency_ms == 0:
                    log_latency_ms = int((time.perf_counter_ns() - start_ns) // 1_000_000)
                if event_name == "answer":
                    answer_data = event_data
                elif event_name == "done":
                    session_id = event_data.get("session_id")
                    total_ms = event_data.get("total_ms")
                    thread_name = event_data.get("thread_name")
                    done_event_data = event_data
                elif event_name in ("step", "agency_start", "agency_responded", "agency_verified"):
                    pipeline_events.append((event_name, event_data))
                with tracer.start_as_current_span("event") as event_span:
                    event_span.set_attribute("stream_event", event_name)
                    event_span.set_attribute("event_data", json.dumps(event_data)[:500])
                if event_name != "done":
                    yield ChatEvent(event_name, event_data)
    except OneChatError as e:
        msg = (
            f"OneChat {version} connection timed out"
            if e.status_code == 504
            else f"OneChat {version} returned {e.status_code}: {e.message}"
        )
        yield ChatEvent("error", {"message": msg, "code": e.status_code})
        yield ChatEvent("done", {"session_id": plan.conversation_id, "total_ms": 0})
        return
    except Exception as e:
        yield ChatEvent("error", {"message": str(e), "code": 500})
        yield ChatEvent("done", {"session_id": plan.conversation_id, "total_ms": 0})
        return

    if answer_data:
        assistant_id = await _persist(
            plan, answer_data=answer_data, session_id=session_id, total_ms=total_ms,
            latency_ms=log_latency_ms, thread_name=thread_name,
            background_tasks=background_tasks, pipeline_events=pipeline_events,
        )
        yield ChatEvent("done", {
            **(done_event_data or {}),
            "session_id": plan.conversation_id,
            "message_id": str(assistant_id),
        })
    elif done_event_data is not None:
        yield ChatEvent("done", {**done_event_data, "session_id": plan.conversation_id})


def _schedule_classification(message_id: str, query: str, answer: str,
                             background_tasks: BackgroundTasks | None) -> None:
    """Schedule category classification on whichever mechanism is available.

    WebSocket routes have no FastAPI BackgroundTasks — there is no response for
    the framework to hang them off — so they fall back to a tracked asyncio task.
    """
    if background_tasks is not None:
        background_tasks.add_task(classify_message_category, message_id, query, answer)
        return
    task = asyncio.create_task(classify_message_category(message_id, query, answer))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _persist(
    plan: TurnPlan, *, answer_data: dict, session_id: str | None, total_ms: int | None,
    latency_ms: int, thread_name: str | None, background_tasks: BackgroundTasks | None,
    pipeline_events: list[tuple[str, dict]] | None = None,
) -> Any:
    """Save the turn via save_turn and write its ConnectionLog."""
    answer = answer_data.get("answer", "").strip()
    errors = answer_data.get("errors", [])
    sections = answer_data.get("sections", [])
    summary = (answer_data.get("summary") or "").strip() or None
    # v5 `references[]` are scoped to `summary`; `sources` keeps its legacy
    # section-derived meaning and stays empty on the stream path.
    summary_references = answer_data.get("references") or []

    agency_ids = []
    for sec in sections:
        if "agencies" in sec:
            agency_ids.extend([ag["id"] for ag in sec["agencies"]])

    response_time = total_ms if total_ms else latency_ms
    agent_steps = build_pipeline_snapshot(pipeline_events or [], errors)

    saved = await save_turn(
        query=plan.query, conversation_id=plan.conversation_id, answer=answer,
        references=[], category=None, agency_ids=agency_ids,
        response_time=response_time, user=plan.user, succeeded=bool(answer),
        external_session_id=session_id, errors=errors, summary=summary,
        summary_references=summary_references, title=thread_name,
        assistant_message_id=plan.assistant_message_id, agent_steps=agent_steps,
    )
    await ConnectionLog.create(
        id=str(generate_uuid()),
        action="query",
        connection_type=f"external_chat_{plan.stream_version}",
        status="success" if answer else "error",
        latency_ms=latency_ms,
        detail=sanitize_body(f"{plan.stream_version} stream query: {plan.query[:100]}"),
        request_body=sanitize_body(
            json.dumps({"query": plan.query, "session_id": plan.conversation_id})
        ),
        response_body=sanitize_body(json.dumps(answer_data, ensure_ascii=False)),
        message_id=saved.user_message_id,
        assistant_message_id=saved.assistant_message_id,
    )
    _schedule_classification(saved.user_message_id, plan.query, answer, background_tasks)
    return saved.assistant_message_id
