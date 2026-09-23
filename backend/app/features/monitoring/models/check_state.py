import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base


class CheckStatus(str, Enum):
    up = "up"
    down = "down"
    unknown = "unknown"


class AgencyCheckState(Base):
    __tablename__ = "agency_check_state"
    __table_args__ = (Index("ix_check_state_next_check_at", "next_check_at"),)

    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agencies.id", ondelete="CASCADE"), primary_key=True,
    )
    interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    next_check_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[CheckStatus] = mapped_column(
        SAEnum(CheckStatus, native_enum=False, create_constraint=False, length=8),
        default=CheckStatus.unknown,
    )
    last_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL", use_alter=True,
                                       name="fk_check_state_incident"), nullable=True,
    )
