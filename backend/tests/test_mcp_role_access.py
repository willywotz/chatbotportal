"""Guard test: MCP `AuthMiddleware` resolves identity from a Keycloak bearer
token (or admits an anonymous caller) and strips agency `Authorization`
headers from every response except an admin's.

The MCP transport (/mcp) is mounted outside FastAPI's dependency injection, so
the REST routers' `require_scope` never runs for it. The only auth gate is
AuthMiddleware in app/mcp/server.py, which verifies the bearer via
`app.auth.keycloak.verify_token` — no DB lookup, no role check beyond
admin/non-admin for the header-stripping trust boundary in `_fetch_agencies`.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.mcp import server


async def _run_auth_middleware(authorization: str | None):
    """Drive AuthMiddleware.on_request with an in-memory fastmcp state dict."""
    state = {}

    async def get_state(key):
        return state.get(key)

    async def set_state(key, value):
        state[key] = value

    ctx = MagicMock()
    ctx.fastmcp_context.get_state = AsyncMock(side_effect=get_state)
    ctx.fastmcp_context.set_state = AsyncMock(side_effect=set_state)
    call_next = AsyncMock(return_value="ok")

    headers = {"Authorization": authorization} if authorization else {}
    with patch.object(server, "get_http_request", return_value=MagicMock(headers=headers)):
        await server.AuthMiddleware().on_request(ctx, call_next)

    return state


@pytest.mark.asyncio
async def test_admin_bearer_resolves_admin_state(make_token):
    token = make_token(role="admin")
    state = await _run_auth_middleware(f"Bearer {token}")
    assert state["user_is_admin"] is True
    assert state["user_id"]


@pytest.mark.asyncio
async def test_non_admin_bearer_resolves_non_admin_state(make_token):
    token = make_token(role="user")
    state = await _run_auth_middleware(f"Bearer {token}")
    assert state["user_is_admin"] is False
    assert state["user_id"]


@pytest.mark.asyncio
async def test_invalid_bearer_is_anonymous():
    state = await _run_auth_middleware("Bearer tcg_totallybogus")
    assert "user_id" not in state
    assert "user_is_admin" not in state


@pytest.mark.asyncio
async def test_no_header_is_anonymous():
    state = await _run_auth_middleware(None)
    assert "user_id" not in state
    assert "user_is_admin" not in state


async def _fetch_with_headers(user_is_admin: bool | None) -> list[dict]:
    agency = {
        "id": "a1",
        "name": "A",
        "status": "active",
        "description": "d",
        "connection_type": "MCP",
        "data_scope": [],
        "endpoint_url": "http://e/",
        "expected_payload": {},
        "api_headers": [{"name": "Authorization", "value": "secret"}],
    }

    ctx = MagicMock()
    ctx.get_state = AsyncMock(side_effect=lambda key: {"user_is_admin": user_is_admin}.get(key))

    with patch.object(server.Agency, "all", return_value=MagicMock(
        values=AsyncMock(return_value=[agency])
    )), patch.object(server, "get_http_request", return_value=MagicMock(
        headers={"X-Forwarded-Host": "example.test"},
        url=MagicMock(scheme="https"),
    )):
        return await server._fetch_agencies(ctx)


@pytest.mark.asyncio
async def test_admin_keeps_agency_auth_header():
    agencies = await _fetch_with_headers(user_is_admin=True)
    assert agencies[0]["api_headers"]


@pytest.mark.asyncio
async def test_non_admin_strips_agency_auth_header():
    agencies = await _fetch_with_headers(user_is_admin=False)
    assert agencies[0]["api_headers"] == []


@pytest.mark.asyncio
async def test_anonymous_strips_agency_auth_header():
    agencies = await _fetch_with_headers(user_is_admin=None)
    assert agencies[0]["api_headers"] == []


@pytest.mark.asyncio
async def test_fetch_agencies_stable_ids_across_payload_keys():
    """Repeated __user_id__ / __conversation_id__ placeholders in one response
    must resolve to the SAME value (ids resolved once, not per key)."""
    ctx = MagicMock()
    ctx.get_state = AsyncMock(return_value=None)

    agency = {
        "id": "a1",
        "name": "A",
        "status": "active",
        "description": "d",
        "connection_type": "API",
        "data_scope": [],
        "endpoint_url": "http://e/",
        "expected_payload": {
            "uid1": "__user_id__",
            "uid2": "prefix-__user_id__",
            "cid1": "__conversation_id__",
            "cid2": "tag-__conversation_id__",
        },
        "api_headers": [],
    }

    with patch.object(server.Agency, "all", return_value=MagicMock(
        values=AsyncMock(return_value=[agency])
    )), patch.object(server, "get_http_request", return_value=MagicMock(
        headers={"X-Forwarded-Host": "example.test"},
        url=MagicMock(scheme="https"),
    )):
        agencies = await server._fetch_agencies(ctx)

    payload = agencies[0]["expected_payload"]

    assert payload["uid1"] == payload["uid2"].removeprefix("prefix-"), (
        f"user_id not stable: uid1={payload['uid1']!r} uid2={payload['uid2']!r}"
    )
    assert payload["cid1"] == payload["cid2"].removeprefix("tag-"), (
        f"conversation_id not stable: cid1={payload['cid1']!r} cid2={payload['cid2']!r}"
    )
    assert "__user_id__" not in payload["uid1"]
    assert "__conversation_id__" not in payload["cid1"]


def test_mcp_server_module_has_no_role_check():
    """Structural guard: AuthMiddleware source must not contain role gating.

    If someone adds a role check to the MCP middleware this test will fail,
    prompting a deliberate decision rather than a silent behaviour change.
    """
    import inspect

    from app.mcp.server import AuthMiddleware

    src = inspect.getsource(AuthMiddleware.on_request)
    role_gate_indicators = [".role", "enforce_role", "require_role", "viewer", "auditor"]
    for indicator in role_gate_indicators:
        assert indicator not in src, (
            f"AuthMiddleware.on_request appears to contain a role check ({indicator!r}). "
            "Read-only roles (viewer, auditor) are intentionally allowed to use MCP. "
            "Update the guard test and this comment if the intent has changed."
        )
