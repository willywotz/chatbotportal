"""Per-agency health aggregated from ConnectionLog, in the frontend contract shape.

Distinct from analytics.get_agency_health (which uses Postgres-only SQL and powers
the separate insights page). This module is SQLite-portable: it fetches rows via the
ORM and aggregates in Python so it runs under the in-memory test DB.
"""
from datetime import datetime, timedelta
from uuid import UUID

from app.config import settings
from app.models import ConnectionLog
from app.utils import get_tz, now

_WINDOW: dict[str, tuple[int, timedelta]] = {
    "24h": (24, timedelta(hours=1)),
    "7d": (7 * 24, timedelta(hours=1)),
    "30d": (30, timedelta(days=1)),
}


async def _rows(agency_id: UUID, since: datetime) -> list[dict]:
    # Normalize to the configured timezone so SQLite string comparison is consistent
    # with stored values (which are recorded in the app timezone via now()).
    tz = get_tz()
    since_local = since.astimezone(tz)
    return await ConnectionLog.filter(
        agency_id=agency_id, created_at__gte=since_local
    ).order_by("created_at").values("status", "latency_ms", "created_at")


async def error_window(agency_id: UUID, reset_at: datetime | None = None) -> tuple[int, int]:
    """Return (checks, failures) over the trailing 24h for an agency."""
    since = now() - timedelta(hours=24)
    if reset_at and reset_at > since:
        since = reset_at
    rows = await _rows(agency_id, since)
    failures = sum(1 for r in rows if r["status"] != "success")
    return len(rows), failures


async def embedded_health(agency_id: UUID, reset_at: datetime | None = None) -> dict:
    since = now() - timedelta(hours=24)
    if reset_at and reset_at > since:
        since = reset_at
    rows = await _rows(agency_id, since)
    if not rows:
        return {"state": "unknown", "uptime_24h": None, "avg_latency_ms_24h": None, "last_check_at": None}
    total = len(rows)
    failures = sum(1 for r in rows if r["status"] != "success")
    uptime = round((total - failures) / total * 100, 1)
    avg_latency = round(sum(r["latency_ms"] for r in rows) / total)
    last = rows[-1]
    if last["status"] != "success":
        state = "down"
    elif uptime < settings.HEALTH_DEGRADED_UPTIME_PCT:
        state = "degraded"
    else:
        state = "up"
    return {
        "state": state,
        "uptime_24h": uptime,
        "avg_latency_ms_24h": avg_latency,
        "last_check_at": last["created_at"],
    }


async def health_history(agency_id: UUID, window: str, reset_at: datetime | None = None) -> list[dict]:
    count, step = _WINDOW.get(window, _WINDOW["24h"])
    end = now()
    start = end - count * step
    row_since = start
    if reset_at and reset_at > start:
        row_since = reset_at
    rows = await _rows(agency_id, row_since)
    buckets = []
    for i in range(count):
        b_start = start + i * step
        buckets.append({
            "bucket_start": b_start, "uptime_pct": 100.0,
            "avg_latency_ms": 0, "checks": 0, "failures": 0, "_lat": 0,
        })
    for r in rows:
        idx = int((r["created_at"] - start) / step)
        if 0 <= idx < count:
            b = buckets[idx]
            b["checks"] += 1
            b["_lat"] += r["latency_ms"]
            if r["status"] != "success":
                b["failures"] += 1
    for b in buckets:
        if b["checks"]:
            b["uptime_pct"] = round((b["checks"] - b["failures"]) / b["checks"] * 100, 1)
            b["avg_latency_ms"] = round(b["_lat"] / b["checks"])
        del b["_lat"]
    return buckets
