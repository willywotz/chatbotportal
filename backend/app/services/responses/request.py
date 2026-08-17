from typing import Any

from app.services.responses.errors import ResponsesApiError

DEFAULT_MODEL_ID = "onechat"


def resolve_model(model: str) -> str:
    """Validate the public model id. Version is chosen elsewhere, per request."""
    if model != DEFAULT_MODEL_ID:
        raise ResponsesApiError(
            f"Unknown model '{model}'. Supported model: {DEFAULT_MODEL_ID}.",
            param="model",
        )
    return model


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
