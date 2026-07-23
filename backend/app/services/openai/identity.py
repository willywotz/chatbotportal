"""Ephemeral temp-user identity for anonymous OpenAI-surface callers."""
from app.auth.security import create_access_token
from app.models.user import User
from app.utils import generate_uuid


async def owner_or_ephemeral(user: User | None) -> tuple[User, str | None]:
    """Return (owner, token). token is None when the caller is authenticated."""
    if user is not None:
        return user, None
    temp = await User.create(
        email=f"anon-{generate_uuid()}@ephemeral.local",
        hashed_password="!",  # unusable — no password login for temp users
        role="user",
        is_ephemeral=True,
    )
    return temp, create_access_token({"sub": str(temp.id)})


def owns(row, user: User | None) -> bool:
    if user is None:
        return False
    return str(row.user_id) == str(user.id) or user.is_admin
