from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class MessageIn(BaseModel):
    """Message as provided when saving a conversation."""
    id: uuid.UUID | None = None
    role: str                          # user | assistant
    content: str
    agent_steps: list[Any] = []
    sources: list[Any] = []
    rating: str | None = None
    feedback_text: str | None = None


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    agent_steps: list[Any]
    sources: list[Any]
    summary: str | None = None
    summary_references: list[Any] = []
    rating: str | None
    feedback_text: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RatingUpdate(BaseModel):
    rating: str                        # up | down
    feedback_text: str | None = None


class SaveConversationRequest(BaseModel):
    """Body for POST /conversations — mirrors save-conversation edge function."""
    title: str = "สนทนาใหม่"
    preview: str | None = None
    agencies: list[str] = []
    status: str = "success"
    response_time: str | None = None
    messages: list[MessageIn] = []


class ConversationResponse(BaseModel):
    id: uuid.UUID
    title: str
    preview: str | None
    agencies: list[str]
    status: str
    message_count: int
    response_time: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HistoryItem(BaseModel):
    """Lightweight item returned by the chat-history endpoint."""
    id: str
    title: str
    preview: str
    date: str
    agencies: list[str]
    status: str
    message_count: int
    response_time: str


class HistoryResponse(BaseModel):
    success: bool
    data: list[HistoryItem]
    total: int
    response_time: int


class DashboardStats(BaseModel):
    total_questions: int
    today_questions: int
    avg_response_time: str
    satisfaction_rate: float


class AgencyUsageItem(BaseModel):
    name: str
    value: int
    fill: str


class WeeklyTrendItem(BaseModel):
    day: str
    questions: int


class CategoryItem(BaseModel):
    category: str
    count: int


class DashboardResponse(BaseModel):
    success: bool
    data: dict
    response_time: int


class DailyTrendItem(BaseModel):
    date: str
    up: int
    down: int
    rate: int


class LowRatedQuestion(BaseModel):
    content: str
    feedback_text: str | None
    agency: str
    created_at: str


class AgencyBreakdownItem(BaseModel):
    agency: str
    up: int
    down: int
    rate: int


class FeedbackStats(BaseModel):
    total_ratings: int
    up_count: int
    down_count: int
    satisfaction_rate: int
    daily_trend: list[DailyTrendItem]
    low_rated_questions: list[LowRatedQuestion]
    agency_breakdown: list[AgencyBreakdownItem]
