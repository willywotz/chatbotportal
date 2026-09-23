"""
ConnectionLog — records every agency connection test or query attempt.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.features.agency.models.agency import Agency
from app.core.base import Base
from app.core.utils import generate_uuid


class ConnectionLog(Base):
    __tablename__ = "connection_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    agency_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agencies.id", ondelete="CASCADE"), nullable=True,
    )
    agency: Mapped["Agency | None"] = relationship(lazy="raise")
    action: Mapped[str] = mapped_column(String(50), default="test")  # test | query
    connection_type: Mapped[str] = mapped_column(String(20))  # MCP | API | A2A
    status: Mapped[str] = mapped_column(String(20))  # success | error
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    request_body: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    assistant_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
