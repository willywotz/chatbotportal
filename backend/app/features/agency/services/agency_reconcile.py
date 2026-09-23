"""Auto-transition agency status from 24h health.

active + error_rate > 50% (>=5 checks)            -> maintenance (auto-set)
rule-set maintenance + error_rate < 50% (>=5)     -> active
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.agency.repositories import agency as agency_repo
from app.features.agency.services.agency_health import error_window

_MIN_CHECKS = 5
_THRESHOLD = 50.0


async def reconcile_statuses(session: AsyncSession) -> None:
    agencies = await agency_repo.list_by_statuses(session, ["active", "maintenance"])
    for ag in agencies:
        checks, failures = await error_window(session, ag.id, ag.stats_reset_at)
        if checks < _MIN_CHECKS:
            continue
        error_rate = failures / checks * 100
        if ag.status == "active" and error_rate > _THRESHOLD:
            ag.status = "maintenance"
            ag.auto_maintenance = True
            await agency_repo.save(session, ag, update_fields=["status", "auto_maintenance", "updated_at"])
            print(f"Auto-maintenance: {ag.name} error_rate={error_rate:.0f}%")
        elif ag.status == "maintenance" and ag.auto_maintenance and error_rate < _THRESHOLD:
            ag.status = "active"
            ag.auto_maintenance = False
            await agency_repo.save(session, ag, update_fields=["status", "auto_maintenance", "updated_at"])
            print(f"Auto-reactivate: {ag.name} error_rate={error_rate:.0f}%")
