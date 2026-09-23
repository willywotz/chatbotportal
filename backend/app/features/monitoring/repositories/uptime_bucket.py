from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete as sa_delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.monitoring.models.uptime_bucket import Granularity, UptimeBucket


def _truncate(ts: datetime, granularity: Granularity) -> datetime:
    if granularity is Granularity.hour:
        return ts.replace(minute=0, second=0, microsecond=0)
    return ts.replace(hour=0, minute=0, second=0, microsecond=0)


async def _upsert(session: AsyncSession, agency_id, ts: datetime, ok: bool, grain: Granularity) -> None:
    bucket_start = _truncate(ts, grain)
    ok_inc = 1 if ok else 0
    stmt = pg_insert(UptimeBucket).values(
        agency_id=agency_id, granularity=grain.value, bucket_start=bucket_start,
        total_checks=1, ok_checks=ok_inc,
    ).on_conflict_do_update(
        constraint="uq_uptime_bucket_grain",
        set_={
            "total_checks": UptimeBucket.total_checks + 1,
            "ok_checks": UptimeBucket.ok_checks + ok_inc,
        },
    )
    await session.execute(stmt)


async def record_check(session: AsyncSession, agency_id, ts: datetime, ok: bool) -> None:
    await _upsert(session, agency_id, ts, ok, Granularity.hour)
    await _upsert(session, agency_id, ts, ok, Granularity.day)


async def uptime_by_agency(session: AsyncSession, since: datetime, granularity: Granularity) -> dict[str, tuple[int, int]]:
    stmt = (
        select(
            UptimeBucket.agency_id,
            func.sum(UptimeBucket.total_checks).label("total"),
            func.sum(UptimeBucket.ok_checks).label("ok"),
        )
        .where(UptimeBucket.granularity == granularity.value)
        .where(UptimeBucket.bucket_start >= since)
        .group_by(UptimeBucket.agency_id)
    )
    rows = (await session.execute(stmt)).all()
    return {str(r.agency_id): (int(r.total), int(r.ok)) for r in rows}


async def prune(session: AsyncSession, *, hour_cutoff: datetime, day_cutoff: datetime) -> int:
    stmt = sa_delete(UptimeBucket).where(
        or_(
            (UptimeBucket.granularity == Granularity.hour.value) & (UptimeBucket.bucket_start < hour_cutoff),
            (UptimeBucket.granularity == Granularity.day.value) & (UptimeBucket.bucket_start < day_cutoff),
        )
    )
    result = await session.execute(stmt, execution_options={"synchronize_session": "fetch"})
    return result.rowcount or 0
