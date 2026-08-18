"""Users router proxied to the Keycloak Admin API.

No live Keycloak: `FakeKeycloak` stands in for the Admin REST API by
monkeypatching keycloak_admin._get/_post/_put/_delete (the seam _request
would otherwise call httpx through). Auth is mocked via the as_principal
fixture, mirroring tests/routers/test_admin_scopes.py.
"""
import re

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import keycloak_admin

_USERS = "/api/v1/users"
_NO_MANAGE_SCOPES = ["agency:list", "conversation:read:own", "conversation:write:own", "message:rate"]


def _resp(status: int, body=None, *, headers=None) -> httpx.Response:
    if body is None:
        return httpx.Response(status, headers=headers)
    return httpx.Response(status, json=body, headers=headers)


class FakeKeycloak:
    """In-memory stand-in for the subset of the Admin REST API this module calls."""

    def __init__(self):
        self.users: dict[str, dict] = {}
        self.role_mappings: dict[str, list[dict]] = {}
        self._roles = {name: {"id": f"role-{name}", "name": name} for name in ("user", "staff", "admin")}
        self._seq = 0

    def seed(self, *, email: str, role: str = "user", enabled: bool = True, display_name: str | None = None) -> str:
        self._seq += 1
        uid = f"kc-{self._seq}"
        rep = {"id": uid, "username": email, "email": email, "enabled": enabled, "createdTimestamp": 0}
        if display_name:
            rep["firstName"] = display_name
        self.users[uid] = rep
        self.role_mappings[uid] = [self._roles[role]]
        return uid

    async def get(self, path, **kwargs):
        if path == "/users":
            params = kwargs.get("params", {})
            reps = list(self.users.values())
            if params.get("search"):
                q = params["search"].lower()
                reps = [r for r in reps if q in r["email"].lower()]
            if "enabled" in params:
                want = params["enabled"] == "true"
                reps = [r for r in reps if r["enabled"] == want]
            return _resp(200, reps)
        if m := re.match(r"^/users/([^/]+)/role-mappings/realm$", path):
            self._require(m.group(1))
            return _resp(200, self.role_mappings.get(m.group(1), []))
        if m := re.match(r"^/users/([^/]+)$", path):
            return _resp(200, self._require(m.group(1)))
        if m := re.match(r"^/roles/([^/]+)$", path):
            return _resp(200, self._roles[m.group(1)])
        raise AssertionError(f"unexpected GET {path}")

    async def post(self, path, **kwargs):
        if path == "/users":
            uid = f"kc-{self._seq + 1}"
            self._seq += 1
            body = dict(kwargs["json"])
            body.pop("credentials", None)
            body.setdefault("enabled", True)
            body["createdTimestamp"] = 0
            self.users[uid] = {"id": uid, **body}
            self.role_mappings[uid] = []
            return _resp(201, headers={"Location": f"http://kc/admin/realms/x/users/{uid}"})
        if m := re.match(r"^/users/([^/]+)/role-mappings/realm$", path):
            uid = m.group(1)
            self._require(uid)
            self.role_mappings.setdefault(uid, []).extend(kwargs["json"])
            return _resp(204)
        raise AssertionError(f"unexpected POST {path}")

    async def put(self, path, **kwargs):
        if m := re.match(r"^/users/([^/]+)/reset-password$", path):
            self._require(m.group(1))
            return _resp(204)
        if m := re.match(r"^/users/([^/]+)$", path):
            self._require(m.group(1)).update(kwargs["json"])
            return _resp(204)
        raise AssertionError(f"unexpected PUT {path}")

    async def delete(self, path, **kwargs):
        if m := re.match(r"^/users/([^/]+)/role-mappings/realm$", path):
            uid = m.group(1)
            self._require(uid)
            drop = {r["name"] for r in kwargs["json"]}
            self.role_mappings[uid] = [r for r in self.role_mappings.get(uid, []) if r["name"] not in drop]
            return _resp(204)
        raise AssertionError(f"unexpected DELETE {path}")

    def _require(self, uid: str) -> dict:
        if uid not in self.users:
            raise keycloak_admin.NotFound(f"user {uid} not found")
        return self.users[uid]


@pytest.fixture
def fake_kc(monkeypatch):
    kc = FakeKeycloak()
    monkeypatch.setattr(keycloak_admin, "_get", kc.get)
    monkeypatch.setattr(keycloak_admin, "_post", kc.post)
    monkeypatch.setattr(keycloak_admin, "_put", kc.put)
    monkeypatch.setattr(keycloak_admin, "_delete", kc.delete)
    return kc


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.usefixtures("db")
async def test_list_users_with_scope_returns_mapped_list(as_principal, fake_kc):
    as_principal(scopes=["user:manage"])
    fake_kc.seed(email="a@example.com", role="admin", display_name="Alice")
    fake_kc.seed(email="b@example.com", role="user")
    async with await _client() as c:
        r = await c.get(_USERS)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    emails = {u["email"] for u in body["data"]}
    assert emails == {"a@example.com", "b@example.com"}
    alice = next(u for u in body["data"] if u["email"] == "a@example.com")
    assert alice["role"] == "admin"
    assert alice["displayName"] == "Alice"
    assert alice["isActive"] is True


@pytest.mark.usefixtures("db")
async def test_list_users_without_scope_403(as_principal, fake_kc):
    as_principal(role="user", scopes=_NO_MANAGE_SCOPES)
    async with await _client() as c:
        r = await c.get(_USERS)
    assert r.status_code == 403


@pytest.mark.usefixtures("db")
async def test_create_user_maps_and_assigns_role(as_principal, fake_kc):
    as_principal(scopes=["user:manage"])
    async with await _client() as c:
        r = await c.post(_USERS, json={
            "email": "new@example.com", "role": "staff", "display_name": "New Person",
            "password": "secret123",
        })
    assert r.status_code == 201
    body = r.json()["user"]
    assert body["email"] == "new@example.com"
    assert body["role"] == "staff"
    uid = body["id"]
    assert {r["name"] for r in fake_kc.role_mappings[uid]} == {"staff"}


@pytest.mark.usefixtures("db")
async def test_get_user(as_principal, fake_kc):
    as_principal(scopes=["user:manage"])
    uid = fake_kc.seed(email="g@example.com", role="user")
    async with await _client() as c:
        r = await c.get(f"{_USERS}/{uid}")
    assert r.status_code == 200
    assert r.json()["email"] == "g@example.com"


@pytest.mark.usefixtures("db")
async def test_get_user_404(as_principal, fake_kc):
    as_principal(scopes=["user:manage"])
    async with await _client() as c:
        r = await c.get(f"{_USERS}/missing")
    assert r.status_code == 404


@pytest.mark.usefixtures("db")
async def test_update_user_profile_and_role(as_principal, fake_kc):
    as_principal(scopes=["user:manage"])
    uid = fake_kc.seed(email="u@example.com", role="user", display_name="Old Name")
    async with await _client() as c:
        r = await c.patch(f"{_USERS}/{uid}", json={"display_name": "New Name", "role": "admin"})
    assert r.status_code == 200
    body = r.json()
    assert body["displayName"] == "New Name"
    assert body["role"] == "admin"
    assert {r["name"] for r in fake_kc.role_mappings[uid]} == {"admin"}


@pytest.mark.usefixtures("db")
async def test_deactivate_calls_set_enabled_false(as_principal, fake_kc):
    as_principal(scopes=["user:manage"])
    uid = fake_kc.seed(email="d@example.com")
    async with await _client() as c:
        r = await c.post(f"{_USERS}/{uid}/deactivate")
    assert r.status_code == 200
    assert r.json()["isActive"] is False
    assert fake_kc.users[uid]["enabled"] is False


@pytest.mark.usefixtures("db")
async def test_activate_calls_set_enabled_true(as_principal, fake_kc):
    as_principal(scopes=["user:manage"])
    uid = fake_kc.seed(email="ac@example.com", enabled=False)
    async with await _client() as c:
        r = await c.post(f"{_USERS}/{uid}/activate")
    assert r.status_code == 200
    assert r.json()["isActive"] is True
    assert fake_kc.users[uid]["enabled"] is True


@pytest.mark.usefixtures("db")
async def test_deactivate_missing_user_404(as_principal, fake_kc):
    as_principal(scopes=["user:manage"])
    async with await _client() as c:
        r = await c.post(f"{_USERS}/missing/deactivate")
    assert r.status_code == 404
