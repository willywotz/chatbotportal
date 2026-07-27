"""Ownership check for OpenAI-surface rows (conversations, responses)."""
from app.models.user import User


def owns(row, user: User | None) -> bool:
    if user is None:
        return False
    return str(row.user_id) == str(user.id) or user.is_admin
