import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.analytics.repositories import analytics as analytics_repo
from app.features.analytics.schemas.insight import AgencyHealthData
from app.features.analytics.schemas.insight import Agency as AgencyHealth
from app.features.agency.services.agency_health import error_window
from app.core.utils import now

logger = logging.getLogger(__name__)


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

    agencies_health = []
    for ag in agencies:
        ag_id = str(ag["id"])
        status = {"active": "healthy"}.get(ag["status"], "down")

        cur_lat = current_latency.get(ag_id) or 0
        avg_lat = avg_latency.get(ag_id) or 0
        # Uptime/error rate over the trailing 24h, honoring per-agency
        # stats_reset_at — identical window to the /agencies embed.
        checks, failures = await error_window(session, ag["id"], ag["stats_reset_at"])
        error_rate = (failures / checks * 100) if checks else 0
        total_day = day_counts.get(ag_id, 0)

        agencies_health.append(AgencyHealth(
            id=ag_id,
            name=ag["name"],
            shortName=ag["short_name"],
            status=status,
            uptime=round(100.0 - error_rate, 2),
            currentLatency=cur_lat // 1,
            avgLatency=avg_lat // 1,
            errorRate=round(error_rate, 2),
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

    return AgencyHealthData(
        agencies=agencies_health,
        historical=historical,
        incidents=[],
        slaCompliance=[],
        generatedAt=now(),
    )
