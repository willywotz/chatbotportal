import asyncio
from datetime import timedelta
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.concurrency import spawn_logged
from app.config import settings
from app.models import Agency, ConnectionLog
from app.services.agency import test_connection
from app.services.agency_reconcile import reconcile_statuses
from app.services.analytics import regenerate_weekly_brief
from app.services.evaluation import run_evaluation
from app.services.event_consumers import register_consumers
from app.services.events import dispatch_pending
from app.services.popular_questions import regenerate as regenerate_popular_questions
from app.services.log_sanitize import sanitize_body
from app.utils import generate_uuid, now

scheduler = AsyncIOScheduler()
sem: asyncio.Semaphore | None = None

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Opentelemetry auto-instrumentation
# ---------------------------------------------------------------------------
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

tracerProvider = TracerProvider(resource=Resource.create({SERVICE_NAME: "backend-scheduler"}))
tracerProvider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint="jaeger:4317", insecure=True)))
tracer = tracerProvider.get_tracer(__name__)

async def _run_agency_item(agency: Agency) -> None:
    """Tracing + dispatch for a single agency health check (time-bounded by caller)."""
    with tracer.start_as_current_span(f"agency_chat_test {agency.name}") as span:
        span.set_attribute("agency.id", str(agency.id))
        span.set_attribute("agency.name", agency.name)
        try:
            if agency.status in ("draft", "disabled"):
                span.set_attribute("agency.skipped", True)
                return
            span.set_attribute("agency.connection_type", agency.connection_type)
            result = await test_connection(agency.connection_type, agency)
            try:
                latency = int(str(result.get("latency", "0")).rstrip("ms"))
            except ValueError:
                latency = 0
            span.set_attribute("agency.api_latency_ms", latency)
            await ConnectionLog.create(
                id=str(generate_uuid()),
                agency=agency,
                action="test",
                connection_type=agency.connection_type,
                status="success" if result.get("success") else "error",
                latency_ms=latency,
                detail=sanitize_body(result.get("error") or "ok"),
            )
        except Exception as e:
            logger.error(f"Error testing agency {agency.name}: {e}")
            span.set_attribute("agency.error", str(e))


async def agency_chat_item(agency: Agency) -> None:
    logger.info(f"Testing agency {agency.name}...")
    async with sem:
        try:
            await asyncio.wait_for(_run_agency_item(agency), timeout=settings.AGENCY_CHAT_TIMEOUT + 5)
        except asyncio.TimeoutError:
            logger.error("agency %s health item timed out", agency.name)


async def agency_chat_test() -> None:
    logger.info("Running agency chat tests...")
    agencies = await Agency.all()
    await asyncio.gather(*[agency_chat_item(ag) for ag in agencies])
    try:
        await reconcile_statuses()
    except Exception as e:
        logger.error(f"Error reconciling agency statuses: {e}")


async def regenerate_brief_job() -> None:
    logger.info("Regenerating weekly brief...")
    try:
        await regenerate_weekly_brief()
    except Exception as e:
        logger.error(f"Error regenerating weekly brief: {e}")


async def regenerate_popular_questions_job() -> None:
    logger.info("Regenerating popular questions...")
    try:
        n = await regenerate_popular_questions()
        logger.info("Popular questions regenerated: %d new row(s)", n)
    except Exception as e:
        logger.error(f"Error regenerating popular questions: {e}")


async def purge_old_connection_logs() -> int:
    logger.info("Purging old connection logs...")
    cutoff = now() - timedelta(days=settings.CONNECTION_LOG_RETENTION_DAYS)
    return await ConnectionLog.filter(created_at__lt=cutoff).delete()


async def start_scheduler() -> None:
    global sem
    sem = asyncio.Semaphore(settings.AGENCY_CHAT_CONCURRENCY)
    register_consumers()  # wire domain-event consumers before the dispatcher runs
    scheduler.add_job(dispatch_pending, IntervalTrigger(seconds=settings.EVENT_DISPATCH_INTERVAL_SECONDS))
    spawn_logged(agency_chat_test(), name="agency_chat_test:startup")
    spawn_logged(regenerate_brief_job(), name="regenerate_brief_job:startup")
    scheduler.add_job(agency_chat_test, IntervalTrigger(minutes=settings.HEALTH_CHECK_INTERVAL_MINUTES))
    scheduler.add_job(regenerate_brief_job, IntervalTrigger(hours=settings.BRIEF_REGEN_INTERVAL_HOURS))
    scheduler.add_job(purge_old_connection_logs, IntervalTrigger(hours=24))
    scheduler.add_job(run_evaluation, IntervalTrigger(hours=settings.EVAL_INTERVAL_HOURS))
    scheduler.add_job(
        regenerate_popular_questions_job,
        IntervalTrigger(hours=settings.POPULAR_QUESTIONS_REGEN_INTERVAL_HOURS),
    )
    scheduler.start()
    logger.info("Scheduler started.")


async def stop_scheduler() -> None:
    scheduler.shutdown()
    logger.info("Scheduler stopped.")
