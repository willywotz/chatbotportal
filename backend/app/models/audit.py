"""Audit trail of sensitive admin/owner actions — who did what to what."""
import uuid
from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.utils import generate_uuid


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)  # who performed it (null = system)
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)  # denormalized — survives user deletion
    action: Mapped[str] = mapped_column(String(50))  # e.g. agency.status_change
    object_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    object_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
