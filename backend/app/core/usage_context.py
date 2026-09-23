"""Request-scoped attribution for LLM usage records.

Each FastAPI request runs in its own asyncio task, which copies the context,
so values set here during request handling are isolated per request.
"""
from contextvars import ContextVar
from uuid import UUID

current_user_id: ContextVar[UUID | None] = ContextVar("current_user_id", default=None)
