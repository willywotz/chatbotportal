from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PopularQuestionAgency(BaseModel):
    id: uuid.UUID
    name: str
    logo: str | None = None


class PopularQuestionCreate(BaseModel):
    """Request body for creating a manual popular question."""
    text: str
    agency_id: uuid.UUID | None = None
    pinned: bool = False
    hidden: bool = False
    sort_order: int = 0


class PopularQuestionUpdate(BaseModel):
    text: str | None = None
    agency_id: uuid.UUID | None = None
    pinned: bool | None = None
    hidden: bool | None = None
    sort_order: int | None = None


class PopularQuestionResponse(BaseModel):
    id: uuid.UUID
    text: str
    agency: PopularQuestionAgency | None = None
    source: str
    pinned: bool
    hidden: bool
    sort_order: int
    score: float | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PopularQuestionListResponse(BaseModel):
    data: list[PopularQuestionResponse]
    total: int
