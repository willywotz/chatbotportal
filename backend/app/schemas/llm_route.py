from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.services.llm.purpose import Purpose


class LLMRouteBase(BaseModel):
    purpose: Purpose
    provider_id: uuid.UUID
    model: str
    timeout_override: float | None = None
    enabled: bool = True


class LLMRouteCreate(LLMRouteBase):
    pass


class LLMRouteUpdate(BaseModel):
    purpose: Purpose | None = None
    provider_id: uuid.UUID | None = None
    model: str | None = None
    timeout_override: float | None = None
    enabled: bool | None = None


class LLMRouteResponse(BaseModel):
    """Response schema — includes the resolved provider name for display."""
    id: uuid.UUID
    purpose: str
    provider_id: uuid.UUID
    provider_name: str
    model: str
    timeout_override: float | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LLMRouteListResponse(BaseModel):
    data: list[LLMRouteResponse]
    total: int


class LLMRouteTestResult(BaseModel):
    """Result of firing a minimal completion through a route (failures ride in `ok`)."""
    ok: bool
    latency_ms: int
    model: str | None = None
    error: str | None = None
