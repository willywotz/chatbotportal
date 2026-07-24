import uuid

from app.services.responses.errors import ResponsesApiError


def parse_uuid(raw: str, prefix: str, *, param: str, code: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw.removeprefix(prefix))
    except (ValueError, AttributeError):
        raise ResponsesApiError(
            f"{param.replace('_', ' ').capitalize()} '{raw}' not found",
            param=param, code=code, status=404,
        )


def conv_id(value) -> str:
    return f"conv_{value}"


def msg_id(value) -> str:
    return f"msg_{value}"
