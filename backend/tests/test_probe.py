"""Tests for the reachability-only probe (app.core.probe).

Every connection type takes the same path: HEAD (GET fallback). Any HTTP
response — including 4xx/5xx — means the endpoint is reachable. Only a
transport failure is an error.
"""

from unittest.mock import patch

import httpx
import pytest

from app.core.probe import probe_reachability as probe

_URL = "https://x.example/chat"


class _Resp:
    def __init__(self, status_code, reason="OK", headers=None):
        self.status_code = status_code
        self.reason_phrase = reason
        self.headers = headers or {"content-type": "application/json", "server": "nginx"}


class _FakeClient:
    def __init__(self, head=None, head_exc=None, get_exc=None):
        self._head = head
        self._head_exc = head_exc
        self._get_exc = get_exc
        self.posted = None
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def head(self, url, headers=None):
        self.calls.append("HEAD")
        if self._head_exc:
            raise self._head_exc
        return self._head

    async def get(self, url, headers=None):
        self.calls.append("GET")
        if self._get_exc:
            raise self._get_exc
        return self._head

    async def post(self, url, headers=None, json=None):
        self.posted = {"url": url, "headers": headers, "json": json}
        raise AssertionError("reachability probe must not POST")


@pytest.mark.asyncio
async def test_head_2xx_is_success():
    fake = _FakeClient(head=_Resp(200, "OK"))
    with patch("app.core.probe.httpx.AsyncClient", return_value=fake):
        res = await probe("API", _URL)
    assert res["success"] is True
    assert res["statusCode"] == 200
    assert fake.calls == ["HEAD"]
    assert fake.posted is None


@pytest.mark.asyncio
async def test_head_405_is_still_reachable():
    fake = _FakeClient(head=_Resp(405, "Method Not Allowed"))
    with patch("app.core.probe.httpx.AsyncClient", return_value=fake):
        res = await probe("API", _URL)
    assert res["success"] is True
    assert res["statusCode"] == 405
    assert fake.posted is None


@pytest.mark.asyncio
async def test_head_500_is_still_reachable():
    fake = _FakeClient(head=_Resp(500, "Internal Server Error"))
    with patch("app.core.probe.httpx.AsyncClient", return_value=fake):
        res = await probe("API", _URL)
    assert res["success"] is True
    assert res["statusCode"] == 500


@pytest.mark.asyncio
async def test_head_raises_then_get_is_success():
    fake = _FakeClient(head=_Resp(200, "OK"), head_exc=httpx.ConnectError("boom"))
    with patch("app.core.probe.httpx.AsyncClient", return_value=fake):
        res = await probe("API", _URL)
    assert res["success"] is True
    assert fake.calls == ["HEAD", "GET"]


@pytest.mark.asyncio
async def test_transport_failure_is_error():
    fake = _FakeClient(head_exc=httpx.ConnectError("refused"), get_exc=httpx.ConnectError("refused"))
    with patch("app.core.probe.httpx.AsyncClient", return_value=fake):
        res = await probe("API", _URL)
    assert res["success"] is False
    assert "refused" in res["error"]
    assert res["steps"][0]["status"] == "error"


@pytest.mark.asyncio
async def test_timeout_reports_the_configured_timeout():
    fake = _FakeClient(head_exc=httpx.TimeoutException("t"), get_exc=httpx.TimeoutException("t"))
    with patch("app.core.probe.httpx.AsyncClient", return_value=fake):
        res = await probe("API", _URL)
    assert res["success"] is False
    assert "timeout" in res["error"].lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(("connection_type", "protocol"), [("API", "REST API"), ("MCP", "MCP"), ("A2A", "A2A")])
async def test_every_type_uses_the_same_probe(connection_type, protocol):
    """MCP no longer sends a JSON-RPC initialize; A2A no longer sends a chat query."""
    fake = _FakeClient(head=_Resp(200, "OK"))
    with patch("app.core.probe.httpx.AsyncClient", return_value=fake):
        res = await probe(connection_type, _URL)
    assert res["success"] is True
    assert res["protocol"] == protocol
    assert fake.calls == ["HEAD"]
    assert fake.posted is None


@pytest.mark.asyncio
async def test_missing_url_is_error():
    res = await probe("API", "")
    assert res["success"] is False
    assert "required" in res["error"].lower()


@pytest.mark.asyncio
async def test_unknown_type_is_error():
    res = await probe("UNKNOWN", _URL)
    assert res["success"] is False
    assert res["protocol"] == "UNKNOWN"
