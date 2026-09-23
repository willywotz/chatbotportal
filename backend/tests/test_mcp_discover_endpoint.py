import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.core.security.principal import Principal
from app.features.agency.routers import spec as spec_router
from app.features.agency.schemas.agency import McpDiscoverRequest

pytestmark = pytest.mark.asyncio


def _admin() -> Principal:
    return Principal(id=str(uuid.uuid4()), email="a@e.com", display_name=None, role="admin", scopes=frozenset())


async def test_mcp_discover_requires_endpoint_url():
    with pytest.raises(HTTPException) as exc:
        await spec_router.mcp_discover(McpDiscoverRequest(endpoint_url=""), _=_admin())
    assert exc.value.status_code == 422


async def test_mcp_discover_returns_tools():
    fake = [{"name": "chat", "description": "d", "input_schema": {}}]
    with patch.object(spec_router, "discover_tools", AsyncMock(return_value=fake)):
        res = await spec_router.mcp_discover(McpDiscoverRequest(endpoint_url="https://mcp.example/sse"), _=_admin())
    assert res.tools[0].name == "chat"


async def test_mcp_discover_connection_error_502():
    with patch.object(spec_router, "discover_tools", AsyncMock(side_effect=RuntimeError("boom"))):
        with pytest.raises(HTTPException) as exc:
            await spec_router.mcp_discover(McpDiscoverRequest(endpoint_url="https://x"), _=_admin())
    assert exc.value.status_code == 502
