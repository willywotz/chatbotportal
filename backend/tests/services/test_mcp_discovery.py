from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.features.agency.services.mcp_discovery import discover_tools


@pytest.mark.asyncio
async def test_discover_tools_maps_fastmcp_tools():
    tool = SimpleNamespace(name="chat_with_fda", description="ask", inputSchema={"type": "object"})
    fake_client = AsyncMock()
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = None
    fake_client.list_tools.return_value = [tool]
    with patch("app.features.agency.services.mcp_discovery.Client", return_value=fake_client):
        tools = await discover_tools("https://mcp.example/sse")
    assert tools[0]["name"] == "chat_with_fda"
    assert tools[0]["description"] == "ask"
    assert tools[0]["input_schema"] == {"type": "object"}


@pytest.mark.asyncio
async def test_discover_tools_handles_dict_tools():
    fake_client = AsyncMock()
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = None
    fake_client.list_tools.return_value = [{"name": "t", "description": "d", "input_schema": {"a": 1}}]
    with patch("app.features.agency.services.mcp_discovery.Client", return_value=fake_client):
        tools = await discover_tools("https://mcp.example/sse")
    assert tools[0]["name"] == "t"
    assert tools[0]["input_schema"] == {"a": 1}
