import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, Enum as SAEnum, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.utils import generate_uuid


class ConnectionType(str, Enum):
    MCP = "MCP"
    API = "API"
    A2A = "A2A"


class AgencyStatus(str, Enum):
    draft = "draft"
    active = "active"
    maintenance = "maintenance"
    disabled = "disabled"


class Agency(Base):
    """Government agency. Mirrors the `agencies` table from the original Supabase schema."""

    __tablename__ = "agencies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255))
    short_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    logo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    connection_type: Mapped[ConnectionType] = mapped_column(
        SAEnum(ConnectionType, native_enum=False, create_constraint=False, length=10),
        default=ConnectionType.API,
    )
    status: Mapped[AgencyStatus] = mapped_column(
        SAEnum(AgencyStatus, native_enum=False, create_constraint=False, length=20),
        default=AgencyStatus.active,
    )
    auto_maintenance: Mapped[bool] = mapped_column(Boolean, default=False)
    stats_reset_at: Mapped[datetime | None] = mapped_column(nullable=True)
    data_scope: Mapped[list] = mapped_column(MutableList.as_mutable(JSONB), default=list)
    color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    endpoint_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    auth_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    auth_header: Mapped[str | None] = mapped_column(String(100), nullable=True)
    base_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_key_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    request_format: Mapped[str | None] = mapped_column(String(50), nullable=True)
    api_endpoints: Mapped[list] = mapped_column(MutableList.as_mutable(JSONB), default=list)
    response_schema: Mapped[list] = mapped_column(MutableList.as_mutable(JSONB), default=list)
    api_spec_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    api_headers: Mapped[list | None] = mapped_column(MutableList.as_mutable(JSONB), nullable=True, default=list)
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    router_hint: Mapped[str] = mapped_column(Text, default="")
    dispatch_timeout_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mcp_tool_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    conformance_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    total_calls: Mapped[int] = mapped_column(Integer, default=0)
    rating_up: Mapped[int] = mapped_column(Integer, default=0)
    rating_down: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    def __str__(self) -> str:
        return f"{self.short_name or self.name} ({self.connection_type})"
