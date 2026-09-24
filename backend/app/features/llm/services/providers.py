from collections.abc import Callable
from dataclasses import dataclass

import openai
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.features.llm.services.errors import LlmError


@dataclass(frozen=True)
class ProviderSpec:
    kind: str
    model_provider: str
    transient_errors: tuple[type[Exception], ...]
    map_error: Callable[[Exception], LlmError | None]
    build_model: Callable[..., BaseChatModel] = init_chat_model


_SPECS: dict[str, ProviderSpec] = {}


def register(spec: ProviderSpec) -> None:
    if spec.kind in _SPECS:
        raise ValueError(f"provider kind already registered: {spec.kind!r}")
    _SPECS[spec.kind] = spec


def get(kind: str) -> ProviderSpec:
    spec = _SPECS.get(kind)
    if spec is None:
        raise LlmError(f"unknown provider kind {kind!r}", kind="config")
    return spec


def known_kinds() -> tuple[str, ...]:
    return tuple(_SPECS)


_OPENAI_TRANSIENT = (
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
    openai.APIConnectionError,
)


def _openai_map_error(exc: Exception) -> LlmError | None:
    if isinstance(exc, openai.APITimeoutError):
        return LlmError(str(exc), kind="timeout", provider="openai")
    if isinstance(exc, openai.RateLimitError):
        return LlmError(str(exc), kind="rate_limited", provider="openai")
    if isinstance(exc, openai.APIConnectionError):
        return LlmError(str(exc), kind="network", provider="openai")
    if isinstance(exc, openai.APIStatusError):
        return LlmError(str(exc), kind="provider",
                        status=getattr(exc, "status_code", None), provider="openai")
    return None


register(ProviderSpec(
    kind="openai",
    model_provider="openai",
    transient_errors=_OPENAI_TRANSIENT,
    map_error=_openai_map_error,
))
