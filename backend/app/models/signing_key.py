"""RS256 signing keys for the OIDC provider.

Generated once and persisted so every uvicorn worker signs and verifies with
the same key. `is_active` marks the current signing key; inactive keys stay
published in JWKS until their tokens have all expired (rotation)."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SigningKey(Base):
    __tablename__ = "signing_keys"

    kid: Mapped[str] = mapped_column(String(64), primary_key=True)
    private_pem: Mapped[str] = mapped_column(Text)
    public_jwk: Mapped[dict] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
