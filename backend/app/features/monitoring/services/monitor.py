from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.agency.models.agency import Agency, AgencyStatus
from app.features.monitoring.models.check_state import AgencyCheckState, CheckStatus
from app.features.monitoring.repositories import uptime_bucket as bucket_repo
from app.features.monitoring.services import incidents as incident_svc
from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.utils import now
from app.core.utils.retry import TRANSIENT, retry_async
from app.features.agency.repositories import agency as agency_repo
from app.features.agency.services.agency import test_connection
from app.features.monitoring.repositories import check_state as cs_repo

logger = logging.getLogger(__name__)


async def record_result(
    session: AsyncSession, state: AgencyCheckState, agency: Agency, *,
    ok: bool, latency_ms: int, detail: str, ts: datetime,
) -> None:
    state.last_checked_at = ts
    state.last_status = CheckStatus.up if ok else CheckStatus.down
    state.last_latency_ms = latency_ms

    await bucket_repo.record_check(session, state.agency_id, ts, ok)
    await incident_svc.apply_transition(
        session, state, ok=ok, detail=detail, failure_threshold=settings.FAILURE_THRESHOLD,
    )

    if ok and agency.status == AgencyStatus.maintenance and agency.auto_maintenance:
        agency.status = AgencyStatus.active
        agency.auto_maintenance = False
    await session.flush()


class _ProbeFailed(Exception):
    def __init__(self, result: dict):
        self.result = result


async def probe_agency(agency, *, retry_max: int, base_delay_ms: int) -> dict:
    async def _once():
        result = await test_connection(agency.connection_type, agency)
        if not result.get("success"):
            raise _ProbeFailed(result)
        return result

    try:
        return await retry_async(
            _once, attempts=retry_max, base_delay=base_delay_ms / 1000,
            retry_on=(_ProbeFailed,) + TRANSIENT,
        )
    except _ProbeFailed as exc:
        return exc.result
    except Exception as exc:  # withinlazy: transport error surfaces as a recorded down
        return {"success": False, "latency": "0ms", "error": str(exc)}


async def _record_one(agency_id) -> bool:
    async with AsyncSessionLocal() as session, session.begin():
        state = await cs_repo.get(session, agency_id)
        agency = await agency_repo.by_id(session, agency_id)
        if state is None or agency is None:
            return False
        raw = await probe_agency(
            agency, retry_max=settings.CHECK_RETRY_MAX, base_delay_ms=settings.CHECK_BACKOFF_BASE_MS,
        )
        ok = bool(raw.get("success"))
        latency_ms = int(str(raw.get("latency", "0")).replace("ms", "") or 0)
        detail = str(raw.get("error") or "ok")
        await record_result(session, state, agency, ok=ok, latency_ms=latency_ms, detail=detail, ts=now())
    return True


async def run_tick() -> int:
    async with AsyncSessionLocal() as session, session.begin():
        await cs_repo.ensure_states(session, settings.DEFAULT_CHECK_INTERVAL_SECONDS)
    async with AsyncSessionLocal() as session, session.begin():
        claimed = await cs_repo.claim_due(
            session, batch=settings.MONITOR_CLAIM_BATCH, jitter_seconds=settings.CHECK_JITTER_SECONDS,
        )
        agency_ids = [c.agency_id for c in claimed]

    sem = asyncio.Semaphore(settings.MONITOR_PROBE_CONCURRENCY)

    async def _guarded(aid):
        async with sem:
            try:
                return await _record_one(aid)
            except Exception:
                logger.exception("monitor record failed for agency %s", aid)
                return False

    results = await asyncio.gather(*[_guarded(aid) for aid in agency_ids])
    return sum(1 for r in results if r)
