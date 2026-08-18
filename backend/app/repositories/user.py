from __future__ import annotations

from tortoise.expressions import Q

from app.models.user import User


async def by_id(user_id) -> User | None:
    return await User.get_or_none(id=user_id)


async def active_by_id(user_id) -> User | None:
    return await User.filter(id=user_id, is_active=True).first()


async def active_by_email(email: str) -> User | None:
    return await User.filter(email=email, is_active=True).first()


async def email_exists(email: str) -> bool:
    return await User.filter(email=email).exists()


async def count_other_active_admins(exclude_id) -> int:
    return await User.filter(role="admin", is_active=True).exclude(id=exclude_id).count()


async def count_all() -> int:
    return await User.all().count()


async def search(*, search_text: str | None, role, is_active: bool | None) -> list[User]:
    qs = User.filter(is_ephemeral=False)
    if search_text:
        qs = qs.filter(Q(email__icontains=search_text) | Q(display_name__icontains=search_text))
    if role:
        qs = qs.filter(role=role)
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    return await qs.order_by("-created_at")


async def create(**fields) -> User:
    return await User.create(**fields)


async def save(user: User, *, update_fields: list[str] | None = None) -> None:
    await user.save(update_fields=update_fields)
