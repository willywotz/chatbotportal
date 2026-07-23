import uuid

import pytest

from app.services.openai.ids import conv_id, msg_id, parse_uuid
from app.services.responses.errors import ResponsesApiError


def test_parse_strips_prefix():
    u = uuid.uuid4()
    assert parse_uuid(f"conv_{u}", "conv_", param="conversation_id", code="conversation_not_found") == u


def test_parse_bad_id_raises_404():
    with pytest.raises(ResponsesApiError) as e:
        parse_uuid("conv_nope", "conv_", param="conversation_id", code="conversation_not_found")
    assert e.value.status == 404 and e.value.code == "conversation_not_found"


def test_format_helpers():
    assert conv_id("x") == "conv_x" and msg_id("x") == "msg_x"
