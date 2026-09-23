import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base
from app.core.utils import generate_uuid


class Granularity(str, Enum):
    hour = "hour"
    day = "day"


class UptimeBucket(Base):
    __tablename__ = "uptime_bucket"
    __table_args__ = (
        UniqueConstraint("agency_id", "granularity", "bucket_start", name="uq_uptime_bucket_grain"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agencies.id", ondelete="CASCADE"),
    )
    granularity: Mapped[Granularity] = mapped_column(
        SAEnum(Granularity, native_enum=False, create_constraint=False, length=8),
    )
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    total_checks: Mapped[int] = mapped_column(Integer, default=0)
    ok_checks: Mapped[int] = mapped_column(Integer, default=0)
