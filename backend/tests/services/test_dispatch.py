"""Tests for app.services.chat.dispatch — agency dispatch module."""
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestBuildApiHeaders:
    def test_default_content_type(self):
        from app.services.chat.dispatch import build_api_headers

        result = build_api_headers(None)
        assert result == {"content-type": "application/json"}

    def test_merges_and_lowercases_custom_headers(self):
        from app.services.chat.dispatch import build_api_headers

        result = build_api_headers([
            {"name": "Authorization", "value": "Bearer token"},
            {"name": "X-Custom", "value": "val"},
        ])
        assert result["content-type"] == "application/json"
        assert result["authorization"] == "Bearer token"
        assert result["x-custom"] == "val"

    def test_empty_list(self):
        from app.services.chat.dispatch import build_api_headers

        result = build_api_headers([])
        assert result == {"content-type": "application/json"}


class TestBuildApiPayload:
    def test_sentinel_query(self):
        from app.services.chat.dispatch import build_api_payload

        result = build_api_payload({"q": "__query__"}, "ภาษี", "conv-1")
        assert result["q"] == "ภาษี"

    def test_sentinel_session_id(self):
        from app.services.chat.dispatch import build_api_payload

        result = build_api_payload({"sid": "__session_id__"}, "q", "conv-1")
        assert result["sid"] == "conv-1"

    def test_sentinel_conversation_id(self):
        from app.services.chat.dispatch import build_api_payload

        result = build_api_payload({"cid": "__conversation_id__"}, "q", "conv-99")
        assert result["cid"] == "conv-99"

    def test_sentinel_user_id_generates_uuid(self):
        from app.services.chat.dispatch import build_api_payload

        result = build_api_payload({"uid": "__user_id__"}, "q", "conv-1")
        assert result["uid"] != "__user_id__"
        assert len(result["uid"]) > 0

    def test_empty_conversation_id_generates_uuid_for_session_sentinel(self):
        from app.services.chat.dispatch import build_api_payload
        import re

        result = build_api_payload({"sid": "__session_id__"}, "q", "")
        # Should be a uuid string
        assert re.match(r"[0-9a-f-]{36}", result["sid"])

    def test_key_name_query_convention(self):
        from app.services.chat.dispatch import build_api_payload

        result = build_api_payload({"query": "placeholder"}, "actual question", "c1")
        assert result["query"] == "actual question"

    def test_key_name_session_id_convention(self):
        from app.services.chat.dispatch import build_api_payload

        result = build_api_payload({"session_id": ""}, "q", "sess-42")
        assert result["session_id"] == "sess-42"

    def test_key_name_conversation_id_convention(self):
        from app.services.chat.dispatch import build_api_payload

        result = build_api_payload({"conversation_id": ""}, "q", "conv-42")
        assert result["conversation_id"] == "conv-42"

    def test_key_name_user_id_convention_generates_uuid(self):
        from app.services.chat.dispatch import build_api_payload

        result = build_api_payload({"user_id": ""}, "q", "c1")
        assert len(result["user_id"]) > 0
        assert result["user_id"] != ""

    def test_passthrough_of_unrelated_keys(self):
        from app.services.chat.dispatch import build_api_payload

        result = build_api_payload({"language": "th", "version": "2"}, "q", "c1")
        assert result["language"] == "th"
        assert result["version"] == "2"

    def test_empty_payload(self):
        from app.services.chat.dispatch import build_api_payload

        result = build_api_payload({}, "q", "c1")
        assert result == {}


class TestSelectMcpTool:
    def _make_tool(self, name):
        t = MagicMock()
        t.name = name
        return t

    def test_picks_chat_like_tool_by_name(self):
        from app.services.chat.dispatch import select_mcp_tool

        tools = [self._make_tool("list_items"), self._make_tool("chat_query")]
        assert select_mcp_tool(tools) == "chat_query"

    def test_picks_ask_tool(self):
        from app.services.chat.dispatch import select_mcp_tool

        tools = [self._make_tool("other"), self._make_tool("ask_agency")]
        assert select_mcp_tool(tools) == "ask_agency"

    def test_picks_query_tool(self):
        from app.services.chat.dispatch import select_mcp_tool

        tools = [self._make_tool("something"), self._make_tool("query_data")]
        assert select_mcp_tool(tools) == "query_data"

    def test_falls_back_to_first_if_no_preferred(self):
        from app.services.chat.dispatch import select_mcp_tool

        tools = [self._make_tool("list_agency"), self._make_tool("get_data")]
        assert select_mcp_tool(tools) == "list_agency"

    def test_empty_list_raises(self):
        from app.services.chat.dispatch import select_mcp_tool

        with pytest.raises(ValueError, match="no MCP tools available"):
            select_mcp_tool([])

    def test_dict_shaped_tool(self):
        from app.services.chat.dispatch import select_mcp_tool

        tools = [{"name": "list_items"}, {"name": "ask_me"}]
        assert select_mcp_tool(tools) == "ask_me"

    def test_mixed_tool_types(self):
        from app.services.chat.dispatch import select_mcp_tool

        obj_tool = self._make_tool("list_items")
        dict_tool = {"name": "query_stuff"}
        assert select_mcp_tool([obj_tool, dict_tool]) == "query_stuff"


class TestBuildMcpArgs:
    def _make_tool_with_schema(self, properties):
        """Make an object tool with inputSchema."""
        t = MagicMock()
        t.inputSchema = {"type": "object", "properties": properties}
        return t

    def _make_dict_tool(self, properties):
        return {"name": "t", "inputSchema": {"type": "object", "properties": properties}}

    def test_maps_to_query_property(self):
        from app.services.chat.dispatch import build_mcp_args

        tool = self._make_tool_with_schema({"query": {"type": "string"}, "other": {"type": "int"}})
        result = build_mcp_args(tool, "test question")
        assert result == {"query": "test question"}

    def test_maps_to_question_property_when_no_query(self):
        from app.services.chat.dispatch import build_mcp_args

        tool = self._make_tool_with_schema({"question": {"type": "string"}})
        result = build_mcp_args(tool, "test question")
        assert result == {"question": "test question"}

    def test_priority_query_over_message(self):
        from app.services.chat.dispatch import build_mcp_args

        tool = self._make_tool_with_schema({
            "message": {"type": "string"},
            "query": {"type": "string"},
        })
        result = build_mcp_args(tool, "hi")
        assert result == {"query": "hi"}

    def test_single_string_property_fallback(self):
        from app.services.chat.dispatch import build_mcp_args

        tool = self._make_tool_with_schema({"payload": {"type": "string"}})
        result = build_mcp_args(tool, "hi")
        assert result == {"payload": "hi"}

    def test_no_arg_when_no_string_properties(self):
        from app.services.chat.dispatch import build_mcp_args

        tool = self._make_tool_with_schema({"count": {"type": "integer"}})
        result = build_mcp_args(tool, "hi")
        assert result == {}

    def test_no_arg_with_empty_schema(self):
        from app.services.chat.dispatch import build_mcp_args

        tool = self._make_tool_with_schema({})
        result = build_mcp_args(tool, "hi")
        assert result == {}

    def test_dict_tool_with_input_schema_key(self):
        from app.services.chat.dispatch import build_mcp_args

        tool = self._make_dict_tool({"query": {"type": "string"}})
        result = build_mcp_args(tool, "hello")
        assert result == {"query": "hello"}

    def test_dict_tool_with_input_schema_snake_key(self):
        from app.services.chat.dispatch import build_mcp_args

        tool = {"name": "t", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}}}
        result = build_mcp_args(tool, "hello")
        assert result == {"query": "hello"}

    def test_no_schema_returns_empty(self):
        from app.services.chat.dispatch import build_mcp_args

        tool = MagicMock(spec=[])  # no inputSchema attr
        result = build_mcp_args(tool, "hi")
        assert result == {}


class TestExtractMcpText:
    def _make_result(self, data=None, structured_content=None, content=None):
        """Build a CallToolResult-like dataclass for testing."""
        @dataclass
        class FakeResult:
            data: Any = None
            structured_content: Any = None
            content: list = field(default_factory=list)

        r = FakeResult()
        if data is not None:
            r.data = data
        if structured_content is not None:
            r.structured_content = structured_content
        if content is not None:
            r.content = content
        return r

    def test_data_str_returned_directly(self):
        from app.services.chat.dispatch import extract_mcp_text

        result = self._make_result(data="hello world")
        assert extract_mcp_text(result) == "hello world"

    def test_data_dict_json_serialized(self):
        from app.services.chat.dispatch import extract_mcp_text

        result = self._make_result(data={"key": "value"})
        assert '"key"' in extract_mcp_text(result)
        assert '"value"' in extract_mcp_text(result)

    def test_structured_content_when_no_data(self):
        from app.services.chat.dispatch import extract_mcp_text

        result = self._make_result(data=None, structured_content={"agency": "test"})
        text = extract_mcp_text(result)
        assert "agency" in text

    def test_content_text_joined(self):
        from app.services.chat.dispatch import extract_mcp_text

        item1 = MagicMock()
        item1.text = "Hello"
        item2 = MagicMock()
        item2.text = "World"
        result = self._make_result(content=[item1, item2])
        text = extract_mcp_text(result)
        assert "Hello" in text
        assert "World" in text

    def test_content_items_without_text_skipped(self):
        from app.services.chat.dispatch import extract_mcp_text

        item_with = MagicMock(spec=["text"])
        item_with.text = "present"
        item_without = MagicMock(spec=[])  # no text attr

        result = self._make_result(content=[item_with, item_without])
        text = extract_mcp_text(result)
        assert "present" in text

    def test_str_fallback(self):
        from app.services.chat.dispatch import extract_mcp_text

        # An object with no data, structured_content, or content
        result = MagicMock(spec=[])
        text = extract_mcp_text(result)
        assert isinstance(text, str)


@pytest.mark.asyncio
async def test_dispatch_api_200_returns_ok():
    from app.services.chat.dispatch import dispatch_api

    route = {
        "agency_name": "TestAgency",
        "endpoint_url": "http://example.com/chat",
        "api_headers": [{"name": "X-Key", "value": "abc"}],
        "expected_payload": {"query": "__query__"},
        "sub_question": "ภาษี",
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"answer": "yes"}

    with patch("app.services.chat.dispatch.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await dispatch_api(route, "conv-1")

    assert result["status"] == "ok"
    assert result["agency"] == "TestAgency"
    assert result["response"] == {"answer": "yes"}


@pytest.mark.asyncio
async def test_dispatch_api_non_200_returns_error():
    from app.services.chat.dispatch import dispatch_api

    route = {
        "agency_name": "TestAgency",
        "endpoint_url": "http://example.com/chat",
        "api_headers": None,
        "expected_payload": {},
        "sub_question": "ภาษี",
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    with patch("app.services.chat.dispatch.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await dispatch_api(route, "conv-1")

    assert result["status"] == "error"
    assert "HTTP 500" in result["response"]
    assert "Internal Server Error" in result["response"]


@pytest.mark.asyncio
async def test_dispatch_api_builds_correct_payload_and_headers():
    from app.services.chat.dispatch import dispatch_api

    route = {
        "agency_name": "Agency",
        "endpoint_url": "http://x/chat",
        "api_headers": [{"name": "Authorization", "value": "Bearer t"}],
        "expected_payload": {"query": "__query__", "session_id": "__session_id__"},
        "sub_question": "what is tax?",
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {}

    with patch("app.services.chat.dispatch.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        await dispatch_api(route, "my-conv-id")

    call = mock_client.post.call_args
    assert call.args[0] == "http://x/chat"
    sent_headers = call.kwargs["headers"]
    assert sent_headers["authorization"] == "Bearer t"
    assert sent_headers["content-type"] == "application/json"
    sent_payload = call.kwargs["json"]
    assert sent_payload["query"] == "what is tax?"
    assert sent_payload["session_id"] == "my-conv-id"


@pytest.mark.asyncio
async def test_dispatch_mcp_happy_path():
    from app.services.chat.dispatch import dispatch_mcp

    route = {
        "agency_name": "MCPAgency",
        "endpoint_url": "http://mcp.example.com/mcp",
    }

    fake_tool = MagicMock()
    fake_tool.name = "query_data"
    fake_tool.inputSchema = {"type": "object", "properties": {"query": {"type": "string"}}}

    @dataclass
    class FakeResult:
        data: Any = "MCP response text"
        structured_content: Any = None
        content: list = field(default_factory=list)
        is_error: bool = False

    fake_result = FakeResult()

    fake_client = AsyncMock()
    fake_client.list_tools = AsyncMock(return_value=[fake_tool])
    fake_client.call_tool = AsyncMock(return_value=fake_result)
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.chat.dispatch.Client", return_value=fake_client):
        result = await dispatch_mcp(route, "ข้อมูลที่ดิน")

    assert result["status"] == "ok"
    assert result["agency"] == "MCPAgency"
    assert result["response"] == "MCP response text"
    fake_client.call_tool.assert_called_once_with("query_data", {"query": "ข้อมูลที่ดิน"})


@pytest.mark.asyncio
async def test_dispatch_mcp_dict_shaped_tool():
    from app.services.chat.dispatch import dispatch_mcp

    route = {
        "agency_name": "DictMCPAgency",
        "endpoint_url": "http://mcp.example.com/mcp",
    }

    dict_tool = {
        "name": "ask_question",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
    }

    @dataclass
    class FakeResult:
        data: Any = "dict tool response"
        structured_content: Any = None
        content: list = field(default_factory=list)
        is_error: bool = False

    fake_result = FakeResult()
    fake_client = AsyncMock()
    fake_client.list_tools = AsyncMock(return_value=[dict_tool])
    fake_client.call_tool = AsyncMock(return_value=fake_result)
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.chat.dispatch.Client", return_value=fake_client):
        result = await dispatch_mcp(route, "question here")

    assert result["status"] == "ok"
    assert result["response"] == "dict tool response"
    fake_client.call_tool.assert_called_once_with("ask_question", {"query": "question here"})


@pytest.mark.asyncio
async def test_dispatch_one_a2a_path():
    from app.services.chat.dispatch import dispatch_one

    route = {
        "connection_type": "A2A",
        "agency_name": "A2AAgency",
        "endpoint_url": "http://a2a.example.com",
        "sub_question": "ทะเบียนรถ",
    }

    with patch("app.services.chat.dispatch.dispatch_a2a", new=AsyncMock(return_value={"agency": "A2AAgency", "status": "ok", "response": {}})) as mock_a2a:
        result = await dispatch_one(route, "conv-1")

    mock_a2a.assert_called_once_with(route, "conv-1")
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_dispatch_one_api_path():
    from app.services.chat.dispatch import dispatch_one

    route = {
        "connection_type": "API",
        "agency_name": "APIAgency",
        "endpoint_url": "http://api.example.com/chat",
        "sub_question": "ภาษี",
        "api_headers": None,
        "expected_payload": {},
    }

    with patch("app.services.chat.dispatch.dispatch_api", new=AsyncMock(return_value={"agency": "APIAgency", "status": "ok", "response": {}})) as mock_api:
        result = await dispatch_one(route, "conv-2")

    mock_api.assert_called_once_with(route, "conv-2")
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_dispatch_one_mcp_path():
    from app.services.chat.dispatch import dispatch_one

    route = {
        "connection_type": "MCP",
        "agency_name": "MCPAgency",
        "endpoint_url": "http://mcp.example.com",
        "sub_question": "test",
    }

    with patch("app.services.chat.dispatch.dispatch_mcp", new=AsyncMock(return_value={"agency": "MCPAgency", "status": "ok", "response": "text"})) as mock_mcp:
        result = await dispatch_one(route, "conv-3")

    mock_mcp.assert_called_once_with(route, "test")
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_dispatch_one_unknown_type():
    from app.services.chat.dispatch import dispatch_one

    route = {
        "connection_type": "UNKNOWN",
        "agency_name": "X",
        "endpoint_url": "http://x",
        "sub_question": "q",
    }

    result = await dispatch_one(route, "conv-1")
    assert result["status"] == "error"
    assert "Unknown connection_type: UNKNOWN" in result["response"]
    assert result["agency"] == "X"


@pytest.mark.asyncio
async def test_dispatch_one_exception_becomes_error():
    from app.services.chat.dispatch import dispatch_one

    route = {
        "connection_type": "MCP",
        "agency_name": "MCPAgency",
        "endpoint_url": "http://mcp.example.com",
        "sub_question": "q",
    }

    with patch("app.services.chat.dispatch.dispatch_mcp", new=AsyncMock(side_effect=ConnectionError("refused"))):
        result = await dispatch_one(route, "conv-1")

    assert result["status"] == "error"
    assert "refused" in result["response"]
    assert result["agency"] == "MCPAgency"


@pytest.mark.asyncio
async def test_dispatch_a2a_posts_and_returns_ok():
    from app.services.chat.dispatch import dispatch_a2a

    route = {"connection_type": "A2A", "sub_question": "q", "agency_name": "A", "endpoint_url": "http://x"}
    mock_response = MagicMock()
    mock_response.json.return_value = {"answer": "ok"}
    with patch("app.services.chat.dispatch.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await dispatch_a2a(route, "conv-1")
    assert result["status"] == "ok"
    assert result["response"] == {"answer": "ok"}
    assert result["agency"] == "A"
    call = mock_client.post.call_args
    assert call.args[0] == "http://x"
    assert "q" in call.kwargs["json"]["query"]
    assert "session_id" in call.kwargs["json"]
    assert call.kwargs["headers"]["Content-Type"] == "application/json"


def test_extract_mcp_text_falsy_data_returned_via_coerce():
    from app.services.chat.dispatch import extract_mcp_text

    @dataclass
    class FakeResult:
        data: Any = 0
        structured_content: Any = None
        content: list = field(default_factory=list)

    result = FakeResult()
    text = extract_mcp_text(result)
    # data == 0 is not None, so _coerce(0) → "0", not str(result)
    assert text == "0"
