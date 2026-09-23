"""
ExecutiveBrief — persisted "AI Weekly Executive Brief" snapshots.

Append-only: each (scheduled or forced) regeneration inserts a row. The current
brief is the latest row by `generated_at`.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base
from app.core.utils import generate_uuid


class ExecutiveBrief(Base):
    __tablename__ = "executive_briefs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok | error
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
