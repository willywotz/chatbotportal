from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiEndpoint(BaseModel):
    method: str = Field(..., examples=["GET", "POST"])
    path: str = Field(..., examples=["/search"])
    description: str = Field(default="")


class ResponseField(BaseModel):
    field: str
    type: str = Field(..., examples=["string", "number", "boolean"])
    description: str = Field(default="")
    example: Any = None

class ApiHeader(BaseModel):
    name: str
    value: str
    description: str = Field(default="")


class AgencyHealthEmbed(BaseModel):
    state: str  # up | degraded | down | unknown
    uptime_24h: float | None = None
    avg_latency_ms_24h: int | None = None
    last_check_at: datetime | None = None


class AgencyBase(BaseModel):
    name: str
    short_name: str | None = None
    logo: str | None = None
    description: str | None = None
    connection_type: str = "API"
    status: str = "active"
    data_scope: list[str] = []
    color: str | None = None

    endpoint_url: str | None = None
    auth_method: str | None = None
    auth_header: str | None = None
    base_path: str | None = None
    api_key_name: str | None = None
    request_format: str | None = None

    api_endpoints: list[ApiEndpoint] = []
    response_schema: list[ResponseField] = []
    api_spec_raw: str | None = None
    expected_payload: dict[str, Any] | None = None
    api_headers: list[ApiHeader] | None = None

    priority: int | None = None
    router_hint: str = ""
    dispatch_timeout_s: int | None = None
    mcp_tool_name: str | None = None


class AgencyCreate(AgencyBase):
    pass


class AgencyUpdate(BaseModel):
    name: str | None = None
    short_name: str | None = None
    logo: str | None = None
    description: str | None = None
    connection_type: str | None = None
    status: str | None = None
    data_scope: list[str] | None = None
    color: str | None = None
    endpoint_url: str | None = None
    auth_method: str | None = None
    auth_header: str | None = None
    base_path: str | None = None
    api_key_name: str | None = None
    request_format: str | None = None
    api_endpoints: list[ApiEndpoint] | None = None
    response_schema: list[ResponseField] | None = None
    api_spec_raw: str | None = None
    expected_payload: dict[str, Any] | None = None
    api_headers: list[ApiHeader] | None = None
    priority: int | None = None
    router_hint: str | None = None
    dispatch_timeout_s: int | None = None
    mcp_tool_name: str | None = None


class AgencyResponse(AgencyBase):
    id: uuid.UUID
    total_calls: int
    created_at: datetime
    updated_at: datetime
    rating_up: int = 0
    rating_down: int = 0
    health: AgencyHealthEmbed | None = None

    model_config = ConfigDict(from_attributes=True)


class AgencyListResponse(BaseModel):
    data: list[AgencyResponse]
    total: int


class HealthHistoryBucket(BaseModel):
    bucket_start: datetime
    uptime_pct: float
    avg_latency_ms: int
    checks: int
    failures: int


class HealthHistoryResponse(BaseModel):
    data: list[HealthHistoryBucket]


class StatusUpdateRequest(BaseModel):
    status: str


class McpDiscoverRequest(BaseModel):
    endpoint_url: str


class McpToolInfo(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class McpDiscoverResponse(BaseModel):
    tools: list[McpToolInfo]


class AgencySummary(BaseModel):
    id: uuid.UUID
    name: str
    short_name: str | None
    logo: str | None
    connection_type: str
    status: str
    data_scope: list[str]
    total_calls: int
    color: str | None

    model_config = ConfigDict(from_attributes=True)
