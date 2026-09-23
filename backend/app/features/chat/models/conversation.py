import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base
from app.core.utils import generate_uuid


class Conversation(Base):
    """Chat conversation — mirrors the `conversations` table from the original Supabase schema."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(500), default="สนทนาใหม่")
    preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    agencies: Mapped[list] = mapped_column(MutableList.as_mutable(JSONB), default=list)  # list[str] — agency names used
    status: Mapped[str] = mapped_column(String(20), default="success")  # success | failed
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    response_time: Mapped[str | None] = mapped_column(String(50), nullable=True)
    external_session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # for tracking sessions with external APIs
    # Tortoise field `metadata` collides with SQLAlchemy's Base.metadata; keep the DB column, rename the attribute.
    meta: Mapped[dict] = mapped_column("metadata", MutableDict.as_mutable(JSONB), default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # soft-delete marker; null = not deleted

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)  # Keycloak sub — not a local User FK

    def __str__(self) -> str:
        return self.title


class Message(Base):
    """Individual chat message within a conversation."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)  # for threading or follow-up messages
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False,
    )
    conversation: Mapped["Conversation"] = relationship(lazy="raise")
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    agent_steps: Mapped[dict | list] = mapped_column(JSONB, default=list)  # {} pipeline snapshot, or [] when none captured
    sources: Mapped[list] = mapped_column(MutableList.as_mutable(JSONB), default=list)  # list of source references
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # v5 executive summary (LLM-written); None in v4 mode
    summary_references: Mapped[list] = mapped_column(MutableList.as_mutable(JSONB), default=list)  # v5 references[] — scoped to `summary` only
    rating: Mapped[str | None] = mapped_column(String(10), nullable=True)  # up | down | None
    feedback_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_time: Mapped[int | None] = mapped_column(Integer, nullable=True)  # in seconds
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)  # สอบถามข้อมูล | ตรวจสอบสถานะ | ขั้นตอนดำเนินการ | กฎหมาย/ระเบียบ
    agency_ids: Mapped[list | None] = mapped_column(MutableList.as_mutable(JSONB), nullable=True, default=list)  # list of agency ids involved in this message
    errors: Mapped[list | None] = mapped_column(MutableList.as_mutable(JSONB), nullable=True, default=list)  # list of error messages if any
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # soft-delete marker; null = not deleted

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)  # Keycloak sub — not a local User FK

    def __str__(self) -> str:
        return f"[{self.role}] {self.content[:60]}"
