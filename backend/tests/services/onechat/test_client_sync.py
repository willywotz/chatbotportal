import httpx
import pytest

from app.services.onechat import OneChatClient, OneChatError


def _transport(recorder: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        recorder["url"] = str(request.url)
        import json
        recorder["json"] = json.loads(request.content)
        recorder["method"] = request.method
        return httpx.Response(200, json={"data": {"answer": "hi", "session_id": "s1"}})
    return httpx.MockTransport(handler)


async def test_chat_v3_posts_to_derived_path_and_forwards_fields():
    rec: dict = {}
    client = OneChatClient("http://oc:8000", transport=_transport(rec))
    out = await client.chat_v3("q", "http://mcp", "conv1")
    assert out == {"data": {"answer": "hi", "session_id": "s1"}}
    assert rec["url"] == "http://oc:8000/v3/chat"
    assert rec["json"] == {"query": "q", "mcp_endpoint_url": "http://mcp", "session_id": "conv1"}


async def test_chat_v1_and_v2_paths():
    rec: dict = {}
    client = OneChatClient("http://oc:8000", transport=_transport(rec))
    await client.chat_v1("q", "http://mcp", "c")
    assert rec["url"] == "http://oc:8000/v1/chat"
    await client.chat_v2("q", "http://mcp", "c")
    assert rec["url"] == "http://oc:8000/v2/chat"


async def test_session_id_omitted_when_none():
    rec: dict = {}
    client = OneChatClient("http://oc:8000", transport=_transport(rec))
    await client.chat_v3("q", "http://mcp", None)
    assert "session_id" not in rec["json"]


async def test_health_returns_status():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://oc:8000/health"
        assert request.method == "GET"
        return httpx.Response(200, json={"status": "ok"})
    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    assert await client.health() == {"status": "ok"}


async def test_non_200_raises_onechat_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")
    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    with pytest.raises(OneChatError) as exc:
        await client.chat_v3("q", "http://mcp", "c")
    assert exc.value.status_code == 503
    assert "upstream down" in exc.value.message


async def test_timeout_maps_to_504():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)
    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    with pytest.raises(OneChatError) as exc:
        await client.chat_v3("q", "http://mcp", "c")
    assert exc.value.status_code == 504


def test_default_base_url_from_settings():
    from app.config import settings
    assert OneChatClient()._base_url == settings.ONECHAT_BASE_URL.rstrip("/")
