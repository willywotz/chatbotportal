"""Async client for the Keycloak Admin REST API.

Backs the admin Users page: the portal no longer stores managed accounts in
its own table, it proxies CRUD to the Keycloak realm. Kept free of FastAPI
imports (Clean Architecture — this is a service, not a router).
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from cachetools import TTLCache

from app.config import settings
from app.schemas.user import Role, UserResponse

_ROLE_NAMES: tuple[Role, ...] = ("admin", "staff", "user")  # precedence when several are assigned


class KeycloakAdminError(Exception):
    """A non-2xx response from the Keycloak Admin API."""

    def __init__(self, message: str, *, status: int):
        super().__init__(message)
        self.status = status


class NotFound(KeycloakAdminError):
    def __init__(self, message: str = "Not found"):
        super().__init__(message, status=404)


_token_cache: TTLCache | None = None


async def _admin_token() -> str:
    """Client-credentials token, cached until shortly before it expires."""
    global _token_cache
    if _token_cache is not None:
        token = _token_cache.get(settings.KEYCLOAK_ADMIN_CLIENT_ID)
        if token is not None:
            return token
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            settings.keycloak_token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.KEYCLOAK_ADMIN_CLIENT_ID,
                "client_secret": settings.KEYCLOAK_ADMIN_CLIENT_SECRET,
            },
        )
    resp.raise_for_status()
    body = resp.json()
    ttl = max(body["expires_in"] - 30, 1)
    _token_cache = TTLCache(maxsize=1, ttl=ttl)
    _token_cache[settings.KEYCLOAK_ADMIN_CLIENT_ID] = body["access_token"]
    return body["access_token"]


async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    token = await _admin_token()
    url = f"{settings.keycloak_admin_base}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.request(method, url, headers=headers, **kwargs)
    if resp.status_code == 404:
        raise NotFound(f"{method} {path}: not found")
    if resp.status_code >= 400:
        raise KeycloakAdminError(f"{method} {path} failed: {resp.status_code} {resp.text}", status=resp.status_code)
    return resp


async def _get(path: str, **kwargs) -> httpx.Response:
    return await _request("GET", path, **kwargs)


async def _post(path: str, **kwargs) -> httpx.Response:
    return await _request("POST", path, **kwargs)


async def _put(path: str, **kwargs) -> httpx.Response:
    return await _request("PUT", path, **kwargs)


async def _delete(path: str, **kwargs) -> httpx.Response:
    return await _request("DELETE", path, **kwargs)


def _display_name(rep: dict) -> str:
    full = f"{rep.get('firstName') or ''} {rep.get('lastName') or ''}".strip()
    return full or rep.get("username") or rep.get("email", "")


def _created_at(rep: dict) -> datetime:
    ms = rep.get("createdTimestamp")
    if ms is None:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _extract_role(role_reps: list[dict]) -> Role:
    names = {r["name"] for r in role_reps}
    for candidate in _ROLE_NAMES:
        if candidate in names:
            return candidate
    return "user"


def _map_user(rep: dict, role: Role) -> UserResponse:
    return UserResponse(
        id=rep["id"],
        email=rep.get("email") or rep.get("username", ""),
        displayName=_display_name(rep),
        role=role,
        avatarUrl=None,
        isActive=bool(rep.get("enabled", True)),
        createdAt=_created_at(rep),
    )


async def _role_of(user_id: str) -> Role:
    role_reps = (await _get(f"/users/{user_id}/role-mappings/realm")).json()
    return _extract_role(role_reps)


async def _assign_role(user_id: str, role: Role) -> None:
    role_rep = (await _get(f"/roles/{role}")).json()
    await _post(f"/users/{user_id}/role-mappings/realm", json=[role_rep])


async def _set_role(user_id: str, role: Role) -> None:
    role_reps = (await _get(f"/users/{user_id}/role-mappings/realm")).json()
    tracked = [r for r in role_reps if r.get("name") in _ROLE_NAMES]
    if tracked:
        await _delete(f"/users/{user_id}/role-mappings/realm", json=tracked)
    await _assign_role(user_id, role)


async def list_users(
    *,
    search: str | None = None,
    role: Role | None = None,
    is_active: bool | None = None,
    limit: int = 1000,
    offset: int = 0,
) -> tuple[list[UserResponse], int]:
    params: dict = {"first": offset, "max": limit}
    if search:
        params["search"] = search
    if is_active is not None:
        params["enabled"] = "true" if is_active else "false"
    reps = (await _get("/users", params=params)).json()
    users = [_map_user(rep, await _role_of(rep["id"])) for rep in reps]
    if role is not None:
        users = [u for u in users if u.role == role]
    return users, len(users)


async def get_user(user_id: str) -> UserResponse:
    rep = (await _get(f"/users/{user_id}")).json()
    return _map_user(rep, await _role_of(user_id))


async def create_user(data) -> UserResponse:
    body: dict = {
        "username": data.email,
        "email": data.email,
        "enabled": True,
        "credentials": [{"type": "password", "value": data.password, "temporary": False}],
    }
    if data.display_name:
        body["firstName"] = data.display_name
    resp = await _post("/users", json=body)
    user_id = resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1]
    await _assign_role(user_id, data.role)
    return await get_user(user_id)


async def update_user(user_id: str, data) -> UserResponse:
    profile: dict = {}
    if data.display_name is not None:
        profile["firstName"] = data.display_name
    if profile:
        await _put(f"/users/{user_id}", json=profile)
    if data.password is not None:
        await _put(f"/users/{user_id}/reset-password", json={"type": "password", "value": data.password, "temporary": False})
    if data.role is not None:
        await _set_role(user_id, data.role)
    return await get_user(user_id)


async def set_enabled(user_id: str, enabled: bool) -> UserResponse:
    await _put(f"/users/{user_id}", json={"enabled": enabled})
    return await get_user(user_id)
