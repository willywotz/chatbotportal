"""
AI Chatbot Portal — FastAPI Backend
=====================================
Stack:  FastAPI · Tortoise ORM · FastMCP
DB:     PostgreSQL

Entry-point:
    uvicorn app.main:app --reload

MCP server:
  - Streamable-HTTP →  /mcp/  (stateless; safe across multiple workers)
REST API is served under /api/v1
"""

import logging
import os
import sys

# 15-Factor XI: treat logs as an event stream. Send every app log to stdout at
# a level taken from the environment (LOG_LEVEL); the platform captures stdout.
logging.basicConfig(
    stream=sys.stdout,
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/health") == -1

logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings, load_settings_from_db
from app.errors import register_error_handlers
from app.database import init_db, close_db
from app.mcp.server import mcp
from app.routers import agencies, audit_log, conversations, messages, dashboard, feedback, auth, chat, connection_logs, executive_summary, insight, popular_questions, public_status, users, settings as settings_router
from app.routers import agent_proxy
from app.routers import llm as llm_router
from app.services.seed import run_seed_admin, run_seed_agencies
from app.services.popular_questions import seed_popular_questions
from app.scheduler import start_scheduler, stop_scheduler
from app.trace_util import QueryTraceparentASGI
from app.utils import generate_uuid, now

# ---------------------------------------------------------------------------
# Opentelemetry auto-instrumentation
# ---------------------------------------------------------------------------
from opentelemetry.sdk.resources import SERVICE_NAME, Resource

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

resource = Resource.create(attributes={
    SERVICE_NAME: "backend"
})

tracerProvider = TracerProvider(resource=resource)
processor = BatchSpanProcessor(OTLPSpanExporter(endpoint="jaeger:4317", insecure=True))
tracerProvider.add_span_processor(processor)
trace.set_tracer_provider(tracerProvider)
HTTPXClientInstrumentor().instrument()

# stateless_http: production runs uvicorn --workers 4 with no session affinity.
# Stateful sessions live in one worker's memory, so a follow-up request routed
# to another worker raises an intermittent "Session terminated". Stateless mode
# uses a fresh transport per request, so any worker can serve any request.
mcp_app = mcp.http_app(path="/", stateless_http=True)

# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await load_settings_from_db()
    await run_seed_admin()
    await run_seed_agencies()
    await start_scheduler()

    async with mcp_app.lifespan(app):
        yield

    await stop_scheduler()
    await close_db()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Central AI Chatbot Portal API.\n\n"
        "**MCP Streamable-HTTP** (stateless): available at `/mcp`.\n\n"
        "**REST API** endpoints are under `/api/v1`."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)
register_error_handlers(app)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# REST routers
# ---------------------------------------------------------------------------

app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(agencies.router, prefix="/api/v1")
app.include_router(conversations.router, prefix="/api/v1")
app.include_router(messages.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(feedback.router, prefix="/api/v1")
app.include_router(connection_logs.router, prefix="/api/v1")
app.include_router(executive_summary.router, prefix="/api/v1")
app.include_router(insight.router, prefix="/api/v1")
app.include_router(popular_questions.router, prefix="/api/v1")
app.include_router(public_status.router, prefix="/api/v1")
app.include_router(settings_router.router, prefix="/api/v1")
app.include_router(audit_log.router, prefix="/api/v1")
app.include_router(llm_router.router, prefix="/api/v1")
app.include_router(agent_proxy.router, prefix="/api/v1")

# ---------------------------------------------------------------------------
# MCP transport — its own auth, independent of the REST routers above.
#
# Mounted sub-apps (app.mount) bypass FastAPI's per-request dependency
# injection by design, so the REST routers' `require_scope` never runs for
# this mount. MCP auth is enforced in app/mcp/server.py via API key: any
# active user is admitted with no role check — see
# backend/tests/test_mcp_role_access.py.
# ---------------------------------------------------------------------------

# MCP server — stateless streamable-HTTP sub-app. QueryTraceparentASGI runs
# first (promotes ?traceparent query param to a header when OneChat's callback
# arrives with no header), then OpenTelemetryMiddleware extracts it.
app.mount("/mcp", QueryTraceparentASGI(OpenTelemetryMiddleware(mcp_app)))

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
async def health_check():
    return "ok\n"

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

FastAPIInstrumentor.instrument_app(
    app,
    excluded_urls="/health,^/health$,/mcp,^/mcp$",
    http_capture_headers_server_request=[".*"],
    http_capture_headers_server_response=[".*"],
)

# Wrap the whole app so a ?traceparent query param is promoted to a header
# before OTel extracts it. OneChat drops the header but keeps the query string,
# so every route (not only /mcp) can continue the trace. `app` stays a FastAPI
# instance; the ASGI server serves `asgi_app`.
asgi_app = QueryTraceparentASGI(app)
