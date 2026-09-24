from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LLMProviderHeader(BaseModel):
    name: str
    value: str


class LLMProviderBase(BaseModel):
    name: str
    provider: str = "openai"
    model: str
    base_url: str | None = None
    api_key: str = ""
    headers: list[LLMProviderHeader] = Field(default_factory=list)
    timeout_seconds: float = 60.0
    max_retries: int = 2
    rate_limit_rps: int | None = None
    rate_limit_rpm: int | None = None
    max_queue_size: int = 50
    enabled: bool = True


class LLMProviderCreate(LLMProviderBase):
    pass


class LLMProviderUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    headers: list[LLMProviderHeader] | None = None
    timeout_seconds: float | None = None
    max_retries: int | None = None
    rate_limit_rps: int | None = None
    rate_limit_rpm: int | None = None
    max_queue_size: int | None = None
    enabled: bool | None = None


class LLMProviderResponse(BaseModel):
    id: uuid.UUID
    name: str
    provider: str
    model: str
    base_url: str | None = None
    api_key: str
    headers: list[LLMProviderHeader] = Field(default_factory=list)
    timeout_seconds: float
    max_retries: int
    rate_limit_rps: int | None = None
    rate_limit_rpm: int | None = None
    max_queue_size: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class LLMProviderListResponse(BaseModel):
    data: list[LLMProviderResponse]
    total: int
