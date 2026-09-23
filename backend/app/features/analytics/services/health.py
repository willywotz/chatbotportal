import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.analytics.repositories import analytics as analytics_repo
from app.features.analytics.schemas.insight import AgencyHealthData
from app.features.analytics.schemas.insight import Agency as AgencyHealth
from app.features.analytics.schemas.insight import Incident as HealthIncident
from app.features.monitoring.models.uptime_bucket import Granularity
from app.features.monitoring.repositories import incident as incident_repo
from app.features.monitoring.repositories import uptime_bucket as bucket_repo
from app.core.utils import now

logger = logging.getLogger(__name__)

_INCIDENTS_LIMIT = 20


def _uptime_pct(counts: dict, agency_id: str) -> float:
    total, ok = counts.get(agency_id, (0, 0))
    return round(ok / total * 100, 2) if total else 100.0


async def get_agency_health(session: AsyncSession) -> AgencyHealthData:
    agencies = await analytics_repo.list_agencies_health_summary(session)

    if not agencies:
        return AgencyHealthData(
            agencies=[],
            historical=[],
            incidents=[],
            slaCompliance=[],
            generatedAt=now(),
        )

    current_cutoff = now() - timedelta(minutes=settings.HEALTH_CHECK_INTERVAL_MINUTES)
    week_cutoff = now() - timedelta(days=7)
    day_cutoff = now() - timedelta(days=settings.AVG_LATENCY_WINDOW_DAYS)

    current_latency = await analytics_repo.connection_log_avg_latency_by_agency(session, current_cutoff)
    avg_latency = await analytics_repo.connection_log_avg_latency_by_agency(session, week_cutoff)
    day_counts = await analytics_repo.connection_log_count_by_agency(session, day_cutoff)
    # Uptime windows from the monitor's uptime buckets — the connection-test probe
    # now records there, not in ConnectionLog. Hour grain for 24h/7d, day grain for 30d.
    uptime_24h = await bucket_repo.uptime_by_agency(session, now() - timedelta(hours=24), Granularity.hour)
    uptime_7d = await bucket_repo.uptime_by_agency(session, now() - timedelta(days=7), Granularity.hour)
    uptime_30d = await bucket_repo.uptime_by_agency(session, now() - timedelta(days=30), Granularity.day)

    agencies_health = []
    for ag in agencies:
        ag_id = str(ag["id"])
        status = {"active": "healthy"}.get(ag["status"], "down")

        cur_lat = current_latency.get(ag_id) or 0
        avg_lat = avg_latency.get(ag_id) or 0
        uptime = _uptime_pct(uptime_24h, ag_id)
        total_day = day_counts.get(ag_id, 0)

        agencies_health.append(AgencyHealth(
            id=ag_id,
            name=ag["name"],
            shortName=ag["short_name"],
            status=status,
            uptime=uptime,
            uptime7d=_uptime_pct(uptime_7d, ag_id),
            uptime30d=_uptime_pct(uptime_30d, ag_id),
            currentLatency=cur_lat // 1,
            avgLatency=avg_lat // 1,
            errorRate=round(100.0 - uptime, 2),
            requestsPerMin=round(total_day / (settings.AVG_LATENCY_WINDOW_DAYS * 1440), 2),
            lastCheckedAt=now(),
        ))

    rawHistorical = await analytics_repo.connection_log_historical(
        session, since=now() - timedelta(days=settings.AVG_LATENCY_WINDOW_DAYS))

    historical = {}
    for entry in rawHistorical:
        date = entry["date"]
        agency_id = str(entry["agency_id"])
        if date not in historical:
            historical[date] = {"time": date}
        historical[date][f"{agency_id}_latency"] = entry["latency"] // 1
        historical[date][f"{agency_id}_uptime"] = round(entry["uptime"], 2)

    historical = sorted(historical.values(), key=lambda x: x["time"])

    incident_rows = await incident_repo.recent(session, limit=_INCIDENTS_LIMIT)
    incidents = [
        HealthIncident(
            agency=name,
            type="downtime",
            severity="critical" if inc.ended_at is None else "warning",
            message=inc.detail or "Service unreachable",
            occurredAt=inc.started_at,
            resolvedAt=inc.ended_at,
        )
        for inc, name in incident_rows
    ]

    return AgencyHealthData(
        agencies=agencies_health,
        historical=historical,
        incidents=incidents,
        slaCompliance=[],
        generatedAt=now(),
    )
