"""Residual pre-migration roles (`viewer`, `auditor`, `agency_owner`) must be
denied by default at the `enforce_role_allowlist` chokepoint, not fail open.

The DB migration that rewrites these rows to `user` hasn't run yet, so a row
with one of these roles can still exist while this code is deployed. The ORM
bypasses the `Role` literal, so `User.create(role="viewer")` is how such a row
is reproduced here.
"""
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.auth.dependencies import enforce_role_allowlist
from app.auth.security import generate_api_key, hash_api_key
from app.models.user import User, UserAPIKey


def _request(method: str, path: str, *, api_key: str) -> Request:
    return Request(
        {"type": "http", "method": method, "path": path,
         "headers": [(b"authorization", f"Bearer {api_key}".encode())], "query_string": b""}
    )


async def _api_key_for_viewer() -> str:
    user = await User.create(email="residual-viewer@x.com", hashed_password="h", role="viewer")
    raw = generate_api_key()
    await UserAPIKey.create(
        user_id=user.id, name="n", key_hash=hash_api_key(raw), key_prefix=raw[:12]
    )
    return raw


async def test_residual_viewer_denied_on_api_keys(db):
    raw = await _api_key_for_viewer()
    with pytest.raises(HTTPException) as e:
        await enforce_role_allowlist(_request("POST", "/api/v1/api-keys/", api_key=raw))
    assert e.value.status_code == 403


async def test_residual_viewer_denied_on_connection_logs(db):
    raw = await _api_key_for_viewer()
    with pytest.raises(HTTPException) as e:
        await enforce_role_allowlist(_request("GET", "/api/v1/connection-logs", api_key=raw))
    assert e.value.status_code == 403


async def test_residual_viewer_allowed_on_chat(db):
    raw = await _api_key_for_viewer()
    assert await enforce_role_allowlist(_request("POST", "/api/v1/chat", api_key=raw)) is None


async def test_residual_viewer_denied_on_dashboard(db):
    raw = await _api_key_for_viewer()
    with pytest.raises(HTTPException) as e:
        await enforce_role_allowlist(_request("GET", "/api/v1/dashboard/stats", api_key=raw))
    assert e.value.status_code == 403
