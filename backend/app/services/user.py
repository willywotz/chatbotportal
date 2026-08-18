"""Session-auth helpers (login-by-email, anonymous sessions).

Admin user management moved to app.services.keycloak_admin — it proxies the
Keycloak Admin REST API instead of this local table.
"""

from __future__ import annotations

import uuid

from app.auth.security import hash_password
from app.config import settings
from app.errors import ApiError, ErrorCode
from app.models.user import User
from app.repositories import user as user_repo

_ANONYMOUS_PASSWORD_PLACEHOLDER = "!"  # anon users never authenticate with a password


def hash_new_password(password: str) -> str:
    if len(password) < settings.MIN_PASSWORD_LENGTH:
        raise ApiError(ErrorCode.INVALID_REQUEST, "รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร", status=400)
    return hash_password(password)


async def get_active_by_email(email: str) -> User | None:
    return await user_repo.active_by_email(email)


async def get_active_by_id(user_id: uuid.UUID | str) -> User | None:
    return await user_repo.active_by_id(user_id)


async def create_anonymous() -> User:
    """Create an ephemeral, password-less user for an anonymous session."""
    return await user_repo.create(
        email=f"anon-{uuid.uuid4().hex}@ephemeral.local",
        is_ephemeral=True, role="user", hashed_password=_ANONYMOUS_PASSWORD_PLACEHOLDER,
    )
