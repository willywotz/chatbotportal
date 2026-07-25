"""Transport-only client for the OneChat service (spec/api/ v1-v5 + health).

Owns payload assembly, HTTP/SSE, and error mapping. No persistence, tracing,
or business logic lives here; callers keep that.
"""
import json
import logging
from typing import AsyncIterator

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SseEvent = tuple[str, dict]

# OneChat upstreams: version → does its /chat endpoint stream SSE?
# v1-v3 return a single JSON envelope; v4-v5 stream. A fact about the service
# (spec/api/), not something the version string implies.
_STREAMS_SSE = {"v1": False, "v2": False, "v3": False, "v4": True, "v5": True}
_VALID_VERSIONS = frozenset(_STREAMS_SSE)
NEWEST_VERSION = "v5"                 # explicit: "newest" is editorial, not max()


def resolve_version(requested: str | None = None) -> str:
    """Per-request override wins; anything invalid/absent → newest."""
    v = (requested or "").strip().lower()
    return v if v in _VALID_VERSIONS else NEWEST_VERSION


class OneChatError(Exception):
    """A non-2xx response or transport failure from onechat."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"OneChat {status_code}: {message}")


def _payload(query: str, mcp_endpoint_url: str, session_id: str | None) -> dict:
    body = {"query": query, "mcp_endpoint_url": mcp_endpoint_url}
    if session_id is not None:
        body["session_id"] = session_id
    return body


def parse_sse_block(block: str) -> SseEvent | None:
    event_name = "message"
    data_line = None
    for line in block.strip().split("\n"):
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_line = line[5:].strip()
    if not data_line:
        return None
    try:
        return event_name, json.loads(data_line)
    except json.JSONDecodeError:
        return None


class OneChatClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        version: str | None = None,
    ):
        self._base_url = (base_url or settings.ONECHAT_BASE_URL).rstrip("/")
        self._transport = transport
        self.version = version or NEWEST_VERSION

    def _open(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout, transport=self._transport)

    async def _post_json(
        self, path: str, query: str, mcp_endpoint_url: str, session_id: str | None
    ) -> dict:
        url = f"{self._base_url}{path}"
        try:
            async with self._open(settings.EXTERNAL_CHAT_TIMEOUT) as client:
                resp = await client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=_payload(query, mcp_endpoint_url, session_id),
                )
        except httpx.ReadTimeout as e:
            raise OneChatError(504, f"onechat {path} timed out") from e
        except httpx.HTTPError as e:
            raise OneChatError(502, f"onechat {path} transport error: {e}") from e
        if resp.status_code != 200:
            raise OneChatError(resp.status_code, resp.text[:200])
        return resp.json()

    async def chat_v1(self, query: str, mcp_endpoint_url: str, session_id: str | None = None) -> dict:
        return await self._post_json("/v1/chat", query, mcp_endpoint_url, session_id)

    async def chat_v2(self, query: str, mcp_endpoint_url: str, session_id: str | None = None) -> dict:
        return await self._post_json("/v2/chat", query, mcp_endpoint_url, session_id)

    async def chat_v3(self, query: str, mcp_endpoint_url: str, session_id: str | None = None) -> dict:
        return await self._post_json("/v3/chat", query, mcp_endpoint_url, session_id)

    async def health(self) -> dict:
        url = f"{self._base_url}/health"
        try:
            async with self._open(settings.EXTERNAL_CHAT_TIMEOUT) as client:
                resp = await client.get(url)
        except httpx.ReadTimeout as e:
            raise OneChatError(504, "onechat /health timed out") from e
        except httpx.HTTPError as e:
            raise OneChatError(502, f"onechat /health transport error: {e}") from e
        if resp.status_code != 200:
            raise OneChatError(resp.status_code, resp.text[:200])
        return resp.json()

    async def stream_v4(
        self, query: str, mcp_endpoint_url: str, session_id: str | None = None
    ) -> AsyncIterator[SseEvent]:
        async for ev in self._stream("/v4/chat", query, mcp_endpoint_url, session_id):
            yield ev

    async def stream_v5(
        self, query: str, mcp_endpoint_url: str, session_id: str | None = None
    ) -> AsyncIterator[SseEvent]:
        async for ev in self._stream("/v5/chat", query, mcp_endpoint_url, session_id):
            yield ev

    async def events(
        self, query: str, mcp_endpoint_url: str, session_id: str | None = None
    ) -> AsyncIterator[SseEvent]:
        """Uniform event stream for this client's pinned version.

        v4/v5 stream SSE; v1/v2/v3 return one JSON envelope, adapted into a
        single `answer` event plus a terminal `done` (spec/api/v3.md: v3 `data`
        equals the streaming `answer` payload).
        """
        v = self.version
        if _STREAMS_SSE[v]:
            async for ev in self._stream(f"/{v}/chat", query, mcp_endpoint_url, session_id):
                yield ev
            return
        envelope = await self._post_json(f"/{v}/chat", query, mcp_endpoint_url, session_id)
        data = envelope.get("data", envelope)
        yield ("answer", data)
        yield ("done", {
            "session_id": data.get("session_id"),
            "total_ms": (data.get("debug") or {}).get("responseTimeMs"),
        })

    def stream_by_version(
        self, version: str, query: str, mcp_endpoint_url: str, session_id: str | None = None
    ) -> AsyncIterator[SseEvent]:
        v = (version or "").strip().lower()
        if v == "v4":
            return self.stream_v4(query, mcp_endpoint_url, session_id)
        if v != "v5":
            logger.warning("Unknown OneChat stream version %r — falling back to v5", version)
        return self.stream_v5(query, mcp_endpoint_url, session_id)

    async def _stream(
        self, path: str, query: str, mcp_endpoint_url: str, session_id: str | None
    ) -> AsyncIterator[SseEvent]:
        url = f"{self._base_url}{path}"
        try:
            async with self._open(settings.V4_STREAM_TIMEOUT) as client:
                async with client.stream(
                    "POST", url,
                    headers={"Content-Type": "application/json"},
                    json=_payload(query, mcp_endpoint_url, session_id),
                ) as resp:
                    if resp.status_code != 200:
                        body = ""
                        try:
                            body = (await resp.aread()).decode()[:200]
                        except Exception:
                            pass
                        raise OneChatError(resp.status_code, body)
                    buffer = ""
                    async for chunk in resp.aiter_text():
                        buffer += chunk
                        while "\n\n" in buffer:
                            block, buffer = buffer.split("\n\n", 1)
                            parsed = parse_sse_block(block)
                            if parsed is not None:
                                yield parsed
        except httpx.ReadTimeout as e:
            raise OneChatError(504, f"onechat {path} timed out") from e


def get_client(version: str | None = None) -> OneChatClient:
    return OneChatClient(version=version or resolve_version())
