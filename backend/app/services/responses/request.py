"""Translate an OpenAI Responses request into portal turn parameters."""
from typing import Any

from app.services.chat.stream import _stream_version
from app.services.responses.errors import ResponsesApiError

DEFAULT_MODEL_ID = "thai-citizen-guide"

# None → follow CHAT_STREAM_VERSION; otherwise pin that OneChat upstream.
MODEL_IDS: dict[str, str | None] = {
    DEFAULT_MODEL_ID: None,
    "thai-citizen-guide-v5": "v5",
    "thai-citizen-guide-v4": "v4",
}


def resolve_model(model: str) -> tuple[str, str]:
    """Return (canonical model id, OneChat stream version) or raise a 400."""
    if model not in MODEL_IDS:
        raise ResponsesApiError(
            f"Unknown model '{model}'. Supported models: {', '.join(sorted(MODEL_IDS))}.",
            param="model",
        )
    pinned = MODEL_IDS[model]
    if pinned is not None:
        return model, pinned
    version = _stream_version()
    return model, version


def extract_query(value: str | list[dict[str, Any]]) -> str:
    """Reduce `input` to the single user question the pipeline takes.

    OneChat keeps conversation history server-side, so only the newest user
    message is forwarded; earlier items in a client-supplied array are context
    the upstream already has.
    """
    if isinstance(value, str):
        query = value.strip()
        if not query:
            raise ResponsesApiError("`input` must not be empty.", param="input")
        return query

    if not value:
        raise ResponsesApiError("`input` must not be empty.", param="input")

    last = value[-1]
    if not isinstance(last, dict) or last.get("role") != "user":
        raise ResponsesApiError(
            "The last item of `input` must be a message with role 'user'.", param="input",
        )

    content = last.get("content", "")
    if isinstance(content, str):
        text = content.strip()
    elif not isinstance(content, list):
        text = ""
    else:
        text = " ".join(
            part.get("text", "").strip()
            for part in content
            if isinstance(part, dict) and part.get("text")
        ).strip()

    if not text:
        raise ResponsesApiError("`input` must not be empty.", param="input")
    return text
