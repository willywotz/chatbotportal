"""Request body for the OpenAI-compatible /responses endpoint.

`extra="ignore"` is deliberate: the OpenAI SDK sends many fields the portal
cannot honour (temperature, tools, max_output_tokens, …) and rejecting them
would break ordinary clients for no benefit.
"""
from typing import Any

from pydantic import BaseModel, ConfigDict


class ResponsesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    model: str = "onechat"
    input: str | list[dict[str, Any]] = ""
    previous_response_id: str | None = None
    conversation: str | None = None
    stream: bool = False
    # Accepted for SDK compatibility; the portal always persists (see the design doc).
    store: bool = True
    # WebSocket warm-up: resolve and warm the session without generating.
    generate: bool = True
    # OneChat upstream override (v1..v5); invalid/absent → newest. Body field so
    # it works on WebSocket, which cannot set headers.
    onechat_version: str | None = None
