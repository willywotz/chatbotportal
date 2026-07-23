from app.services.responses.errors import ResponsesApiError


def validate_metadata(md: dict | None) -> dict:
    if md is None:
        return {}
    if not isinstance(md, dict) or len(md) > 16:
        raise ResponsesApiError("`metadata` must be a map of at most 16 entries.",
                                param="metadata")
    for k, v in md.items():
        if not isinstance(k, str) or len(k) > 64 or not isinstance(v, str) or len(v) > 512:
            raise ResponsesApiError(
                "`metadata` keys must be <=64 chars and values <=512-char strings.",
                param="metadata")
    return md
