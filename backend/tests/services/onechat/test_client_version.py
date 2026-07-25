import httpx
import pytest

from app.services.onechat.client import (
    NEWEST_VERSION, OneChatClient, get_client, resolve_version,
)


def test_resolve_version_uses_valid_override():
    assert resolve_version("v3") == "v3"
    assert resolve_version(" V4 ") == "v4"


def test_resolve_version_defaults_to_newest():
    assert resolve_version(None) == NEWEST_VERSION
    assert resolve_version("") == NEWEST_VERSION
    assert resolve_version("bogus") == NEWEST_VERSION


def test_client_pins_version_from_constructor():
    assert OneChatClient("http://oc:8000", version="v3").version == "v3"


def test_client_defaults_version_to_newest():
    assert OneChatClient("http://oc:8000").version == NEWEST_VERSION


def _sync_transport(payload: dict, rec: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if rec is not None:
            rec["url"] = str(request.url)
        return httpx.Response(200, json=payload)
    return httpx.MockTransport(handler)


async def test_events_v3_unwraps_data_into_answer_and_done():
    rec: dict = {}
    payload = {"data": {"answer": "hi", "sections": [],
                        "session_id": "s1", "debug": {"responseTimeMs": 1234}}}
    client = OneChatClient("http://oc:8000", transport=_sync_transport(payload, rec), version="v3")
    events = [ev async for ev in client.events("q", "http://mcp", "c")]
    assert rec["url"] == "http://oc:8000/v3/chat"
    assert events[0] == ("answer", payload["data"])
    assert events[1] == ("done", {"session_id": "s1", "total_ms": 1234})


async def test_events_sync_tolerates_missing_data_envelope_and_debug():
    payload = {"answer": "hi", "session_id": "s1"}   # no "data", no "debug"
    client = OneChatClient("http://oc:8000", transport=_sync_transport(payload), version="v2")
    events = [ev async for ev in client.events("q", "http://mcp", None)]
    assert events[0] == ("answer", payload)
    assert events[1] == ("done", {"session_id": "s1", "total_ms": None})


async def test_events_v5_streams_sse():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://oc:8000/v5/chat"
        body = 'event: answer\ndata: {"answer": "hi"}\n\nevent: done\ndata: {"session_id": "s1"}\n\n'
        return httpx.Response(200, text=body)
    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler), version="v5")
    events = [ev async for ev in client.events("q", "http://mcp", "c")]
    assert ("answer", {"answer": "hi"}) in events
