from datetime import timedelta
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.concurrency import spawn_logged
from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.repositories import connection_log as connection_log_repo
from app.features.analytics.services import regenerate_weekly_brief
from app.features.agency.services.evaluation import run_evaluation
from app.core.event_consumers import register_consumers
from app.core.events import dispatch_pending
from app.features.analytics.services.popular_questions import regenerate as regenerate_popular_questions
from app.features.monitoring.services.monitor import run_tick as monitor_tick_impl
from app.features.monitoring.repositories import uptime_bucket as uptime_bucket_repo
from app.core.utils import now

scheduler = AsyncIOScheduler()

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

async def monitor_tick() -> None:
    logger.info("Running uptime monitor tick...")
    try:
        recorded = await monitor_tick_impl()
        logger.info("Monitor tick recorded %d agency check(s)", recorded)
    except Exception as e:
        logger.error("Monitor tick failed: %s", e)


async def regenerate_brief_job() -> None:
    logger.info("Regenerating weekly brief...")
    try:
        async with AsyncSessionLocal() as session, session.begin():
            await regenerate_weekly_brief(session)
    except Exception as e:
        logger.error(f"Error regenerating weekly brief: {e}")


async def regenerate_popular_questions_job() -> None:
    logger.info("Regenerating popular questions...")
    try:
        async with AsyncSessionLocal() as session, session.begin():
            n = await regenerate_popular_questions(session)
        logger.info("Popular questions regenerated: %d new row(s)", n)
    except Exception as e:
        logger.error(f"Error regenerating popular questions: {e}")


async def purge_old_connection_logs() -> int:
    logger.info("Purging old connection logs...")
    async with AsyncSessionLocal() as session, session.begin():
        removed_logs = await connection_log_repo.delete_older_than(
            session, now() - timedelta(days=settings.CONNECTION_LOG_RETENTION_DAYS),
        )
        await uptime_bucket_repo.prune(
            session,
            hour_cutoff=now() - timedelta(days=settings.UPTIME_BUCKET_HOUR_RETENTION_DAYS),
            day_cutoff=now() - timedelta(days=settings.UPTIME_BUCKET_DAY_RETENTION_DAYS),
        )
    return removed_logs


async def start_scheduler() -> None:
    register_consumers()  # wire domain-event consumers before the dispatcher runs
    scheduler.add_job(dispatch_pending, IntervalTrigger(seconds=settings.EVENT_DISPATCH_INTERVAL_SECONDS))
    spawn_logged(monitor_tick(), name="monitor_tick:startup")
    spawn_logged(regenerate_brief_job(), name="regenerate_brief_job:startup")
    scheduler.add_job(monitor_tick, IntervalTrigger(seconds=settings.MONITOR_TICK_SECONDS))
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
