import uuid

from pydantic import BaseModel
from typing import Any

class ChatRequest(BaseModel):
    query: str
    conversation_id: str | None = None
    stream: bool = False
    model: str | None = None

class ChatResponseData(BaseModel):
    message_id: uuid.UUID
    answer: str
    references: list[dict[str, Any]]
    agentSteps: list[dict[str, Any]]
    agencies: list[dict[str, Any]]
    confidence: float
    cached: bool = False

class ChatResponse(BaseModel):
    success: bool
    data: ChatResponseData
    conversation_id: str
    responseTime: int
    
    error: str | None = None