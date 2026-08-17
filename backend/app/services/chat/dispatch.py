"""Agency dispatch module for the chat pipeline.

Handles A2A, API, and MCP connection types. graph.py calls dispatch_one for
each route and this module owns all per-protocol I/O.

# NOTE: MCP tool selection / arg mapping are heuristic (speculative) — the real
# agency MCP tool schema is unknown without a live server.
"""
import json
import uuid

import httpx
from fastmcp import Client

from app.config import settings
from app.utils.retry import retry_async

# Priority-ordered property names that map to the sub-question
_QUERY_PROPS = ("query", "question", "message", "text", "input")


def _tool_name(tool) -> str:
    """Return the name string from either a fastmcp Tool object or a dict."""
    if isinstance(tool, dict):
        return tool["name"]
    return tool.name


def _dispatch_timeout(route: dict) -> int:
    return route.get("dispatch_timeout_s") or settings.AGENCY_CHAT_TIMEOUT


def build_api_headers(api_headers: list[dict] | None) -> dict:
    headers: dict[str, str] = {"content-type": "application/json"}
    for h in (api_headers or []):
        headers[h["name"].lower()] = h["value"]
    return headers


def build_api_payload(
    expected_payload: dict,
    sub_question: str,
    conversation_id: str,
) -> dict:
    payload: dict = {}
    for k, v in expected_payload.items():
        if v == "__query__":
            payload[k] = sub_question
        elif v in ("__session_id__", "__conversation_id__"):
            payload[k] = conversation_id or str(uuid.uuid4())
        elif v == "__user_id__":
            payload[k] = str(uuid.uuid4())
        elif k == "query":
            payload[k] = sub_question
        elif k in ("session_id", "conversation_id"):
            payload[k] = conversation_id or str(uuid.uuid4())
        elif k == "user_id":
            payload[k] = str(uuid.uuid4())
        else:
            payload[k] = v
    return payload


def select_mcp_tool(tools: list) -> str:
    """Select the best tool name from a list of fastmcp Tool objects or dicts.

    Prefers tools whose name contains chat/ask/query/question/answer.
    Falls back to the first tool. Raises ValueError if the list is empty.
    """
    if not tools:
        raise ValueError("no MCP tools available")
    preferred = ("chat", "ask", "query", "question", "answer")
    for tool in tools:
        name = _tool_name(tool)
        if any(p in name.lower() for p in preferred):
            return name
    return _tool_name(tools[0])


def build_mcp_args(tool, sub_question: str) -> dict:
    """Build call arguments for an MCP tool from the tool's input schema."""
    if isinstance(tool, dict):
        schema = tool.get("inputSchema") or tool.get("input_schema") or {}
    else:
        schema = getattr(tool, "inputSchema", None) or {}

    properties: dict = schema.get("properties", {})
    if not properties:
        return {}

    # Prefer priority names
    for prop in _QUERY_PROPS:
        if prop in properties:
            return {prop: sub_question}

    # Single string property fallback
    string_props = [k for k, v in properties.items() if v.get("type") == "string"]
    if len(string_props) == 1:
        return {string_props[0]: sub_question}

    return {}


def _coerce(value) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def extract_mcp_text(result) -> str:
    """Extract a string response from a fastmcp CallToolResult-like object."""
    data = getattr(result, "data", None)
    if data is not None:
        return _coerce(data)

    structured = getattr(result, "structured_content", None)
    if structured is not None:
        return _coerce(structured)

    content = getattr(result, "content", None)
    if content is not None:
        parts = [item.text for item in content if hasattr(item, "text")]
        return "\n".join(parts)

    return str(result)


async def dispatch_a2a(route: dict, conversation_id: str) -> dict:
    sub_q = route["sub_question"]

    async def _call():
        async with httpx.AsyncClient(timeout=settings.A2A_DISPATCH_TIMEOUT) as client:
            return await client.post(
                route["endpoint_url"],
                json={
                    "session_id": str(uuid.uuid4()),
                    "query": f"ให้ระบุแหล่งที่มาของข้อมูลในคำตอบด้วยเสมอ\n\nคำถาม: {sub_q}",
                },
                headers={"Content-Type": "application/json"},
            )

    resp = await retry_async(_call)
    return {"agency": route["agency_name"], "response": resp.json(), "status": "ok"}


async def dispatch_api(route: dict, conversation_id: str) -> dict:
    headers = build_api_headers(route.get("api_headers"))
    payload = build_api_payload(
        route.get("expected_payload") or {},
        route["sub_question"],
        conversation_id,
    )

    async def _call():
        async with httpx.AsyncClient(timeout=_dispatch_timeout(route)) as client:
            return await client.post(route["endpoint_url"], headers=headers, json=payload)

    resp = await retry_async(_call)
    if resp.status_code == 200:
        return {"agency": route["agency_name"], "response": resp.json(), "status": "ok"}
    return {
        "agency": route["agency_name"],
        "response": f"HTTP {resp.status_code}: {resp.text}",
        "status": "error",
    }


async def dispatch_mcp(route: dict, sub_question: str) -> dict:
    async with Client(route["endpoint_url"]) as client:
        tools = await client.list_tools()
        tool_name = select_mcp_tool(tools)
        tool_obj = next((t for t in tools if _tool_name(t) == tool_name), None)
        args = build_mcp_args(tool_obj, sub_question)
        result = await client.call_tool(tool_name, args)
    return {
        "agency": route["agency_name"],
        "response": extract_mcp_text(result),
        "status": "ok",
    }


async def dispatch_one(route: dict, conversation_id: str) -> dict:
    conn = route["connection_type"]
    name = route["agency_name"]
    try:
        if conn == "A2A":
            return await dispatch_a2a(route, conversation_id)
        if conn == "API":
            return await dispatch_api(route, conversation_id)
        if conn == "MCP":
            return await dispatch_mcp(route, route["sub_question"])
        return {"agency": name, "response": f"Unknown connection_type: {conn}", "status": "error"}
    except Exception as e:
        return {"agency": name, "response": str(e), "status": "error"}
