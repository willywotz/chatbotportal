"""Drain the streaming turn pipeline into a single JSON result.

The sync transport reuses run_turn (so persistence, caching, and classification
stay identical to the stream path) and folds its events into a version-faithful
payload.
"""
from dataclasses import dataclass

from app.services.chat.pipeline_snapshot import build_pipeline_snapshot
from app.services.chat.stream import Scheduler, TurnPlan, run_turn

_PIPELINE_EVENTS = ("step", "agency_start", "agency_responded", "agency_verified")


@dataclass
class TurnResult:
    answer_data: dict
    agent_steps: dict | list
    message_id: str
    total_ms: int
    cached: bool
    error: dict | None


async def collect_turn(
    plan: TurnPlan, *, schedule: Scheduler | None
) -> TurnResult:
    answer_data: dict = {}
    pipeline_events: list[tuple[str, dict]] = []
    message_id = str(plan.assistant_message_id)
    total_ms = 0
    error: dict | None = None

    async for event in run_turn(plan, schedule=schedule):
        if event.name == "answer":
            answer_data = event.data
        elif event.name in _PIPELINE_EVENTS:
            pipeline_events.append((event.name, event.data))
        elif event.name == "done":
            message_id = event.data.get("message_id", message_id)
            total_ms = event.data.get("total_ms") or 0
        elif event.name == "error":
            error = event.data

    return TurnResult(
        answer_data=answer_data,
        agent_steps=build_pipeline_snapshot(pipeline_events, answer_data.get("errors", [])),
        message_id=message_id,
        total_ms=total_ms,
        cached=plan.cached is not None,
        error=error,
    )
