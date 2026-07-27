"""Map the public `model` id to a OneChat upstream version.

OpenAI-style: `onechat` (or absent) means newest; `onechat-vN` pins a version.
Anything unrecognized falls back to newest, matching resolve_version()'s lenient
contract so a typo degrades instead of erroring.
"""
from app.services.onechat import resolve_version

_PREFIX = "onechat-"


def resolve_model_version(model: str | None) -> str:
    m = (model or "").strip().lower()
    suffix = m[len(_PREFIX):] if m.startswith(_PREFIX) else ""
    return resolve_version(suffix)
