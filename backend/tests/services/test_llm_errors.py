import httpx
import pytest
from pydantic import BaseModel, ValidationError
from langchain_core.exceptions import OutputParserException
from app.features.llm.services.errors import LlmError, to_llm_error


class _Spec:
    def map_error(self, exc):
        return None


def test_llm_error_passthrough():
    original = LlmError("boom", kind="queue_full")
    assert to_llm_error(original, _Spec()) is original


def test_spec_mapping_wins():
    class Spec:
        def map_error(self, exc):
            return LlmError("mapped", kind="rate_limited")
    assert to_llm_error(RuntimeError("x"), Spec()).kind == "rate_limited"


def test_output_parser_exception_is_parse():
    assert to_llm_error(OutputParserException("bad"), _Spec()).kind == "parse"


def test_validation_error_is_parse():
    class M(BaseModel):
        x: int
    try:
        M(x="not-int")
    except ValidationError as e:
        assert to_llm_error(e, _Spec()).kind == "parse"


def test_httpx_timeout_is_timeout():
    assert to_llm_error(httpx.TimeoutException("t"), _Spec()).kind == "timeout"


def test_httpx_transport_is_network():
    assert to_llm_error(httpx.ConnectError("c"), _Spec()).kind == "network"


def test_unknown_is_unknown():
    assert to_llm_error(RuntimeError("?"), _Spec()).kind == "unknown"
