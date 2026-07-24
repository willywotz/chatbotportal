import pytest

from app.services.openai.metadata import validate_metadata
from app.services.responses.errors import ResponsesApiError


def test_none_becomes_empty():
    assert validate_metadata(None) == {}


def test_accepts_valid_map():
    assert validate_metadata({"topic": "demo"}) == {"topic": "demo"}


def test_rejects_too_many_keys():
    with pytest.raises(ResponsesApiError) as e:
        validate_metadata({f"k{i}": "v" for i in range(17)})
    assert e.value.param == "metadata"


def test_rejects_oversize_value():
    with pytest.raises(ResponsesApiError):
        validate_metadata({"k": "x" * 513})
