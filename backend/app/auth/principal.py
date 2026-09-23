"""The authenticated identity shared by every protected route.

Kept free of framework and provider imports so both the OIDC token layer and
the FastAPI dependencies can depend on it without a cycle.
"""
from __future__ import annotations

from dataclasses import dataclass


class InvalidToken(Exception):
    """The presented token failed verification."""


@dataclass(frozen=True)
class Principal:
    id: str
    email: str | None
    display_name: str | None
    role: str
    scopes: frozenset[str]

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
