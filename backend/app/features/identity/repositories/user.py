from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.identity.models.user import User, UserRole


async def get(session: AsyncSession, user_id: uuid.UUID | str) -> User | None:
    return await session.get(User, user_id)


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(func.lower(User.email) == email.lower())
    return (await session.execute(stmt)).scalar_one_or_none()


async def create(
    session: AsyncSession,
    *,
    email: str,
    password_hash: str,
    role: UserRole,
    display_name: str | None = None,
    is_active: bool = True,
) -> User:
    user = User(
        email=email,
        password_hash=password_hash,
        display_name=display_name,
        role=role,
        is_active=is_active,
    )
    session.add(user)
    await session.flush()
    return user


async def list_users(
    session: AsyncSession,
    *,
    search: str | None = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
) -> list[User]:
    stmt = select(User)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.display_name.ilike(like)))
    if role is not None:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active.is_(is_active))
    stmt = stmt.order_by(User.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def delete(session: AsyncSession, user: User) -> None:
    await session.delete(user)
    await session.flush()


async def admin_exists(session: AsyncSession) -> bool:
    stmt = select(func.count()).select_from(User).where(User.role == UserRole.admin)
    return bool((await session.execute(stmt)).scalar_one())
