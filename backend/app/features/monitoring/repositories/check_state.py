from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import func, literal, select
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


async def claim_due(session: AsyncSession, *, batch: int, jitter_seconds: int) -> list[AgencyCheckState]:
    stmt = (
        select(AgencyCheckState)
        .join(Agency, Agency.id == AgencyCheckState.agency_id)
        .where(Agency.status.notin_(_SKIP_STATUSES))
        .where(AgencyCheckState.next_check_at <= now())
        .order_by(AgencyCheckState.next_check_at)
        .limit(batch)
        .with_for_update(skip_locked=True, of=AgencyCheckState)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    moment = now()
    for st in rows:
        jitter = random.uniform(0, jitter_seconds) if jitter_seconds else 0
        st.next_check_at = moment + timedelta(seconds=st.interval_seconds + jitter)
    await session.flush()
    return rows
