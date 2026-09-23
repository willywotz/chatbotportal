from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.oauth import OAuthAuthCode, OAuthRefreshToken


async def create_auth_code(
    session: AsyncSession,
    *,
    code_hash: str,
    user_id: uuid.UUID,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    scope: str,
    expires_at: datetime,
) -> OAuthAuthCode:
    row = OAuthAuthCode(
        code_hash=code_hash,
        user_id=user_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        scope=scope,
        expires_at=expires_at,
        consumed=False,
    )
    session.add(row)
    await session.flush()
    return row


async def get_auth_code(session: AsyncSession, code_hash: str) -> OAuthAuthCode | None:
    return await session.get(OAuthAuthCode, code_hash)


async def create_refresh_token(
    session: AsyncSession,
    *,
    token_hash: str,
    user_id: uuid.UUID,
    client_id: str,
    scope: str,
    expires_at: datetime,
) -> OAuthRefreshToken:
    row = OAuthRefreshToken(
        token_hash=token_hash,
        user_id=user_id,
        client_id=client_id,
        scope=scope,
        expires_at=expires_at,
        revoked=False,
    )
    session.add(row)
    await session.flush()
    return row


async def get_refresh_token(session: AsyncSession, token_hash: str) -> OAuthRefreshToken | None:
    stmt = select(OAuthRefreshToken).where(OAuthRefreshToken.token_hash == token_hash)
    return (await session.execute(stmt)).scalar_one_or_none()


async def revoke_user_tokens(session: AsyncSession, user_id: uuid.UUID) -> None:
    stmt = (
        update(OAuthRefreshToken)
        .where(OAuthRefreshToken.user_id == user_id, OAuthRefreshToken.revoked.is_(False))
        .values(revoked=True)
    )
    await session.execute(stmt)
    await session.flush()
