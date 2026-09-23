"""Fire-and-forget task helper that never silently drops exceptions."""
import asyncio
import logging

from opentelemetry import trace

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)
_pending: set[asyncio.Task] = set()


def spawn_logged(coro, *, name: str) -> asyncio.Task:
    """Schedule `coro` as a background task; log any exception it raises.

    Holds a strong reference until the task completes (asyncio only keeps weak
    references, so an un-retained task can be garbage-collected mid-flight).
    """
    task = asyncio.ensure_future(coro)
    task.set_name(name)
    _pending.add(task)

    def _done(t: asyncio.Task) -> None:
        _pending.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.error("background task %s failed: %s", name, exc, exc_info=exc)
            trace.get_current_span().add_event(
                "background_task.failed", {"task": name, "error": type(exc).__name__}
            )

    task.add_done_callback(_done)
    return task
