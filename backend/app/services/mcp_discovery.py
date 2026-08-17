from typing import Any

from fastmcp import Client


def _get(tool: Any, attr: str, *alt_keys: str) -> Any:
    if isinstance(tool, dict):
        for k in (attr, *alt_keys):
            if k in tool:
                return tool[k]
        return None
    return getattr(tool, attr, None)


async def discover_tools(endpoint_url: str) -> list[dict]:
    async with Client(endpoint_url) as client:
        tools = await client.list_tools()
    result = []
    for t in tools:
        schema = _get(t, "inputSchema", "input_schema") or {}
        result.append({
            "name": _get(t, "name") or "",
            "description": _get(t, "description") or "",
            "input_schema": schema,
        })
    return result
