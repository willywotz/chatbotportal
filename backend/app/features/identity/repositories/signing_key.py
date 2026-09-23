from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.identity.models.signing_key import SigningKey


async def get_active(session: AsyncSession) -> SigningKey | None:
    stmt = select(SigningKey).where(SigningKey.is_active.is_(True)).order_by(SigningKey.created_at.desc())
    return (await session.execute(stmt)).scalars().first()


async def all_keys(session: AsyncSession) -> list[SigningKey]:
    stmt = select(SigningKey).order_by(SigningKey.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def create(session: AsyncSession, *, kid: str, private_pem: str, public_jwk: dict) -> SigningKey:
    key = SigningKey(kid=kid, private_pem=private_pem, public_jwk=public_jwk, is_active=True)
    session.add(key)
    await session.flush()
    return key
