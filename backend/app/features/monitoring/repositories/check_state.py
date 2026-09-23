from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import func, literal, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.agency.models.agency import Agency
from app.features.monitoring.models.check_state import AgencyCheckState, CheckStatus
from app.core.utils import now

_SKIP_STATUSES = ("draft", "disabled")


async def ensure_states(session: AsyncSession, default_interval_seconds: int) -> int:
    src = select(Agency.id, literal(default_interval_seconds), func.now())
    stmt = (
        pg_insert(AgencyCheckState)
        .from_select(["agency_id", "interval_seconds", "next_check_at"], src)
        .on_conflict_do_nothing(index_elements=["agency_id"])
    )
    result = await session.execute(stmt)
    return result.rowcount or 0


async def get(session: AsyncSession, agency_id) -> AgencyCheckState | None:
    return await session.get(AgencyCheckState, agency_id)


async def get_for_update(session: AsyncSession, agency_id) -> AgencyCheckState | None:
    stmt = (
        select(AgencyCheckState)
        .where(AgencyCheckState.agency_id == agency_id)
        .with_for_update()
    )
    return (await session.execute(stmt)).scalars().first()


async def claim_due(
    session: AsyncSession, *, batch: int, jitter_seconds: int, lease_seconds: int = 0,
) -> list[AgencyCheckState]:
    moment = now()
    stmt = (
        select(AgencyCheckState)
        .join(Agency, Agency.id == AgencyCheckState.agency_id)
        .where(Agency.status.notin_(_SKIP_STATUSES))
        .where(or_(
            AgencyCheckState.next_check_at <= moment,
            AgencyCheckState.leased_until <= moment,
        ))
        .order_by(AgencyCheckState.next_check_at)
        .limit(batch)
        .with_for_update(skip_locked=True, of=AgencyCheckState)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    for st in rows:
        jitter = random.uniform(0, jitter_seconds) if jitter_seconds else 0
        st.next_check_at = moment + timedelta(seconds=st.interval_seconds + jitter)
        if lease_seconds:
            st.leased_until = moment + timedelta(seconds=lease_seconds)
    await session.flush()
    return rows
