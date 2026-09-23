"""Seed the first administrator so a fresh deployment is reachable.

Creates SEED_ADMIN_EMAIL with role admin only when no admin account exists.
Idempotent: a no-op once any admin is present."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.identity.oidc.passwords import hash_password
from app.core.config import settings
from app.features.identity.models.user import UserRole
from app.features.identity.repositories import user as user_repo

logger = logging.getLogger(__name__)


async def seed_admin_user(session: AsyncSession) -> None:
    if await user_repo.admin_exists(session):
        return
    await user_repo.create(
        session,
        email=settings.SEED_ADMIN_EMAIL,
        password_hash=hash_password(settings.SEED_ADMIN_PASSWORD),
        role=UserRole.admin,
        display_name="Administrator",
    )
    logger.info("seeded initial admin account: %s", settings.SEED_ADMIN_EMAIL)
