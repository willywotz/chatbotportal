from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class LLMProviderBase(BaseModel):
    name: str
    base_url: str
    api_key: str = ""
    auth_header: str = "Authorization"
    auth_scheme: str = "Bearer"
    timeout_seconds: float = 60.0
    request_usage: bool = False
    rate_limit_rps: int | None = None
    rate_limit_rpm: int | None = None
    max_queue_size: int = 50
    enabled: bool = True


class LLMProviderCreate(LLMProviderBase):
    pass


class LLMProviderUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    auth_header: str | None = None
    auth_scheme: str | None = None
    timeout_seconds: float | None = None
    request_usage: bool | None = None
    rate_limit_rps: int | None = None
    rate_limit_rpm: int | None = None
    max_queue_size: int | None = None
    enabled: bool | None = None


class LLMProviderResponse(BaseModel):
    """Response schema — `api_key` is always masked, never the real secret."""
    id: uuid.UUID
    name: str
    base_url: str
    api_key: str
    auth_header: str
    auth_scheme: str
    timeout_seconds: float
    request_usage: bool
    rate_limit_rps: int | None = None
    rate_limit_rpm: int | None = None
    max_queue_size: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class LLMProviderListResponse(BaseModel):
    data: list[LLMProviderResponse]
    total: int
