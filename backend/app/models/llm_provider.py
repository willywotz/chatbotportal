import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.utils import generate_uuid


class LlmProvider(Base):
    __tablename__ = "llm_providers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    base_url: Mapped[str] = mapped_column(String(500))
    api_key: Mapped[str] = mapped_column(Text, default="")
    auth_header: Mapped[str] = mapped_column(String(100), default="Authorization")
    auth_scheme: Mapped[str] = mapped_column(String(50), default="Bearer")
    timeout_seconds: Mapped[float] = mapped_column(Float, default=60.0)
    request_usage: Mapped[bool] = mapped_column(Boolean, default=False)
    rate_limit_rps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_limit_rpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_queue_size: Mapped[int] = mapped_column(Integer, default=50)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
