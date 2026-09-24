from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.features.llm.services.purpose import Purpose


class LLMBindingBase(BaseModel):
    purpose: Purpose
    provider_id: uuid.UUID
    model_override: str | None = None
    fallback_binding_id: uuid.UUID | None = None
    timeout_override: float | None = None
    enabled: bool = True


class LLMBindingCreate(LLMBindingBase):
    pass


class LLMBindingUpdate(BaseModel):
    provider_id: uuid.UUID | None = None
    model_override: str | None = None
    fallback_binding_id: uuid.UUID | None = None
    timeout_override: float | None = None
    enabled: bool | None = None


class LLMBindingResponse(BaseModel):
    id: uuid.UUID
    purpose: str
    provider_id: uuid.UUID
    provider_name: str
    model: str
    fallback_binding_id: uuid.UUID | None = None
    timeout_override: float | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class LLMBindingListResponse(BaseModel):
    data: list[LLMBindingResponse]
    total: int


class LLMBindingTestResult(BaseModel):
    ok: bool
    latency_ms: int
    model: str | None = None
    error: str | None = None
