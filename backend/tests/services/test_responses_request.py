"""Mapping an OpenAI request onto a portal turn."""

import pytest

from app.schemas.responses import ResponsesRequest
from app.services.responses.errors import ResponsesApiError
from app.services.responses.request import extract_query, resolve_model


def test_resolve_model_accepts_onechat():
    assert resolve_model("onechat") == "onechat"


def test_resolve_model_rejects_old_thai_citizen_guide_ids():
    for old in ("thai-citizen-guide", "thai-citizen-guide-v5", "thai-citizen-guide-v4"):
        with pytest.raises(ResponsesApiError) as exc:
            resolve_model(old)
        assert exc.value.status == 400
        assert exc.value.param == "model"


def test_resolve_model_rejects_unknown_model():
    with pytest.raises(ResponsesApiError) as exc:
        resolve_model("gpt-5")
    assert exc.value.param == "model"


def test_onechat_version_defaults_to_none():
    req = ResponsesRequest.model_validate({"model": "onechat", "input": "hi"})
    assert req.onechat_version is None


def test_onechat_version_is_accepted():
    req = ResponsesRequest.model_validate(
        {"model": "onechat", "input": "hi", "onechat_version": "v3"})
    assert req.onechat_version == "v3"


def test_string_input_is_the_query():
    assert extract_query("บัตรประชาชนหาย") == "บัตรประชาชนหาย"


def test_array_input_uses_the_last_user_message():
    value = [
        {"role": "user", "content": [{"type": "input_text", "text": "first"}]},
        {"role": "assistant", "content": [{"type": "output_text", "text": "answer"}]},
        {"role": "user", "content": [{"type": "input_text", "text": "second"}]},
    ]
    assert extract_query(value) == "second"


def test_array_input_joins_multiple_text_parts():
    value = [{"role": "user", "content": [
        {"type": "input_text", "text": "part one"},
        {"type": "input_text", "text": "part two"},
    ]}]
    assert extract_query(value) == "part one part two"


def test_array_input_accepts_a_plain_string_content():
    assert extract_query([{"role": "user", "content": "hello"}]) == "hello"


def test_array_input_rejects_a_trailing_assistant_message():
    value = [{"role": "assistant", "content": [{"type": "output_text", "text": "a"}]}]
    with pytest.raises(ResponsesApiError) as exc:
        extract_query(value)
    assert exc.value.param == "input"


def test_array_input_rejects_null_content():
    value = [{"role": "user", "content": None}]
    with pytest.raises(ResponsesApiError) as exc:
        extract_query(value)
    assert exc.value.param == "input"


def test_array_input_rejects_non_iterable_content():
    value = [{"role": "user", "content": 5}]
    with pytest.raises(ResponsesApiError) as exc:
        extract_query(value)
    assert exc.value.param == "input"


def test_array_input_rejects_a_non_dict_item():
    with pytest.raises(ResponsesApiError) as exc:
        extract_query([None])
    assert exc.value.param == "input"


def test_empty_input_is_rejected():
    for value in ("", "   ", []):
        with pytest.raises(ResponsesApiError):
            extract_query(value)


def test_unsupported_fields_are_accepted_and_ignored():
    req = ResponsesRequest.model_validate({
        "model": "onechat",
        "input": "hi",
        "temperature": 0.7,
        "tools": [{"type": "function", "name": "x"}],
        "max_output_tokens": 100,
    })
    assert req.input == "hi"
    assert not hasattr(req, "temperature")


def test_store_and_generate_default_true():
    req = ResponsesRequest.model_validate({"model": "onechat", "input": "hi"})
    assert req.store is True
    assert req.generate is True
    assert req.stream is False
