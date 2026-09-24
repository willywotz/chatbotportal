import httpx
from pydantic import ValidationError
from langchain_core.exceptions import OutputParserException


class LlmError(Exception):
    def __init__(self, message, *, kind, status=None, provider=None):
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.provider = provider


def to_llm_error(exc, spec):
    if isinstance(exc, LlmError):
        return exc
    mapped = spec.map_error(exc)
    if mapped is not None:
        return mapped
    if isinstance(exc, (OutputParserException, ValidationError)):
        return LlmError(str(exc), kind="parse")
    if isinstance(exc, httpx.TimeoutException):
        return LlmError(str(exc), kind="timeout")
    if isinstance(exc, httpx.TransportError):
        return LlmError(str(exc), kind="network")
    return LlmError(str(exc), kind="unknown")
