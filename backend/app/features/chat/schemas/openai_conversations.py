from typing import Any

from pydantic import BaseModel, ConfigDict


class MessageItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str = "message"
    role: str
    content: Any = ""


class ConversationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    metadata: dict | None = None
    items: list[MessageItem] | None = None


class ConversationUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    metadata: dict | None = None


class ItemsCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    items: list[MessageItem]
