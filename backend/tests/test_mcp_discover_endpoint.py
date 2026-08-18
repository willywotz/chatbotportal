import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.auth.keycloak import Principal
from app.routers import agencies as r
from app.schemas.agency import McpDiscoverRequest


async def _admin():
    return Principal(id=str(uuid.uuid4()), email="a@e.com", display_name=None, role="admin", scopes=frozenset())


@pytest.mark.asyncio
async def test_mcp_discover_requires_endpoint_url(db):
    admin = await _admin()
    with pytest.raises(HTTPException) as exc:
        await r.mcp_discover(McpDiscoverRequest(endpoint_url=""), _=admin)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_mcp_discover_returns_tools(db):
    admin = await _admin()
    fake = [{"name": "chat", "description": "d", "input_schema": {}}]
    with patch("app.routers.agencies.spec.discover_tools", AsyncMock(return_value=fake)):
        res = await r.mcp_discover(McpDiscoverRequest(endpoint_url="https://mcp.example/sse"), _=admin)
    assert res.tools[0].name == "chat"


@pytest.mark.asyncio
async def test_mcp_discover_connection_error_502(db):
    admin = await _admin()
    with patch("app.routers.agencies.spec.discover_tools", AsyncMock(side_effect=RuntimeError("boom"))):
        with pytest.raises(HTTPException) as exc:
            await r.mcp_discover(McpDiscoverRequest(endpoint_url="https://x"), _=admin)
    assert exc.value.status_code == 502
