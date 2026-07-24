"""Transport-only client for the OneChat service (spec/api/ v1-v5 + health).

Owns payload assembly, HTTP/SSE, and error mapping. No persistence, tracing,
or business logic lives here; callers keep that.
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SseEvent = tuple[str, dict]


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


class OneChatClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._base_url = (base_url or settings.ONECHAT_BASE_URL).rstrip("/")
        self._transport = transport

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

    async def chat_v1(self, query, mcp_endpoint_url, session_id=None) -> dict:
        return await self._post_json("/v1/chat", query, mcp_endpoint_url, session_id)

    async def chat_v2(self, query, mcp_endpoint_url, session_id=None) -> dict:
        return await self._post_json("/v2/chat", query, mcp_endpoint_url, session_id)

    async def chat_v3(self, query, mcp_endpoint_url, session_id=None) -> dict:
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


def get_client() -> OneChatClient:
    return OneChatClient()
