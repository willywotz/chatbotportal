import httpx
import pytest

from app.services.onechat import OneChatClient, OneChatError
from app.services.onechat.client import parse_sse_block

SSE_BODY = (
    "event: status\ndata: {\"stage\": \"routing\"}\n\n"
    "event: answer\ndata: {\"answer\": \"final\"}\n\n"
    "event: done\ndata: {\"session_id\": \"s1\", \"total_ms\": 12}\n\n"
)


def _sse_transport(recorder: dict, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        recorder["url"] = str(request.url)
        if status != 200:
            return httpx.Response(status, text="boom")
        return httpx.Response(200, text=SSE_BODY)
    return httpx.MockTransport(handler)


def test_parse_sse_block():
    assert parse_sse_block("event: answer\ndata: {\"answer\": \"x\"}") == ("answer", {"answer": "x"})
    assert parse_sse_block("data: {\"a\": 1}") == ("message", {"a": 1})
    assert parse_sse_block("event: ping\n(no data)") is None
    assert parse_sse_block("data: not-json") is None


async def test_stream_v5_yields_events_in_order():
    rec: dict = {}
    client = OneChatClient("http://oc:8000", transport=_sse_transport(rec))
    events = [ev async for ev in client.stream_v5("q", "http://mcp", "c")]
    assert rec["url"] == "http://oc:8000/v5/chat"
    assert events == [
        ("status", {"stage": "routing"}),
        ("answer", {"answer": "final"}),
        ("done", {"session_id": "s1", "total_ms": 12}),
    ]


async def test_stream_by_version_selects_v4():
    rec: dict = {}
    client = OneChatClient("http://oc:8000", transport=_sse_transport(rec))
    _ = [ev async for ev in client.stream_by_version("v4", "q", "http://mcp", "c")]
    assert rec["url"] == "http://oc:8000/v4/chat"


async def test_stream_by_version_unknown_falls_back_to_v5():
    rec: dict = {}
    client = OneChatClient("http://oc:8000", transport=_sse_transport(rec))
    _ = [ev async for ev in client.stream_by_version("bogus", "q", "http://mcp", "c")]
    assert rec["url"] == "http://oc:8000/v5/chat"


async def test_stream_non_200_raises_onechat_error():
    rec: dict = {}
    client = OneChatClient("http://oc:8000", transport=_sse_transport(rec, status=500))
    with pytest.raises(OneChatError) as exc:
        _ = [ev async for ev in client.stream_v5("q", "http://mcp", "c")]
    assert exc.value.status_code == 500


async def test_stream_read_timeout_maps_to_504():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)
    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    with pytest.raises(OneChatError) as exc:
        _ = [ev async for ev in client.stream_v5("q", "http://mcp", "c")]
    assert exc.value.status_code == 504
