"""Guard test: read-only roles (viewer, auditor) are NOT rejected by MCP auth.

The MCP transport (/mcp) is mounted outside FastAPI's dependency injection, so
the role chokepoint (enforce_role_allowlist) never runs for it. The only auth
gate is AuthMiddleware in app/mcp/server.py,
which checks that the API key is usable and the user is active — no role
check at all.

These tests reproduce the exact DB lookups performed by AuthMiddleware to
confirm that viewer and auditor keys resolve to a live User object and are
not filtered out by any role condition.
"""

import pytest

from app.auth.security import generate_api_key, hash_api_key
from app.models.user import User, UserAPIKey


async def _resolve_user_via_mcp_auth(raw_key: str) -> User | None:
    """Mirror the AuthMiddleware lookup in app/mcp/server.py lines 52-56."""
    api_key = await UserAPIKey.filter(key_hash=hash_api_key(raw_key)).first()
    if api_key and api_key.is_usable():
        return await User.filter(id=api_key.user_id, is_active=True).first()
    return None


async def _make_user_with_key(email: str, role: str) -> tuple[User, str]:
    user = await User.create(email=email, hashed_password="h", role=role)
    raw = generate_api_key()
    await UserAPIKey.create(
        user_id=user.id, name="test", key_hash=hash_api_key(raw), key_prefix=raw[:12]
    )
    return user, raw


@pytest.mark.asyncio
async def test_viewer_api_key_resolves_via_mcp_auth(db):
    user, raw = await _make_user_with_key("viewer@x.com", "viewer")
    resolved = await _resolve_user_via_mcp_auth(raw)
    assert resolved is not None
    assert resolved.id == user.id


@pytest.mark.asyncio
async def test_auditor_api_key_resolves_via_mcp_auth(db):
    user, raw = await _make_user_with_key("auditor@x.com", "auditor")
    resolved = await _resolve_user_via_mcp_auth(raw)
    assert resolved is not None
    assert resolved.id == user.id


@pytest.mark.asyncio
async def test_invalid_key_returns_none(db):
    resolved = await _resolve_user_via_mcp_auth("tcg_totallybogus")
    assert resolved is None


@pytest.mark.asyncio
async def test_inactive_user_returns_none(db):
    user = await User.create(
        email="inactive@x.com", hashed_password="h", role="viewer", is_active=False
    )
    raw = generate_api_key()
    await UserAPIKey.create(
        user_id=user.id, name="test", key_hash=hash_api_key(raw), key_prefix=raw[:12]
    )
    resolved = await _resolve_user_via_mcp_auth(raw)
    assert resolved is None


@pytest.mark.asyncio
async def test_fetch_agencies_stable_ids_across_payload_keys():
    """Repeated __user_id__ / __conversation_id__ placeholders in one response
    must resolve to the SAME value (ids resolved once, not per key)."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.mcp import server

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
