"""Users router backed by the local `users` table (self-hosted IdP).

Auth is mocked via the as_principal fixture; accounts are seeded directly
through the user repository against the test's rolled-back session."""
from app.features.identity.oidc.passwords import hash_password
from app.features.identity.models.user import UserRole
from app.features.identity.repositories import user as user_repo

_USERS = "/api/v1/users"
_NO_MANAGE_SCOPES = ["agency:list", "conversation:read:own", "conversation:write:own", "message:rate"]


async def _seed(session, *, email, role=UserRole.user, is_active=True, display_name=None):
    return await user_repo.create(
        session, email=email, password_hash=hash_password("pw"),
        role=role, display_name=display_name, is_active=is_active,
    )


async def test_list_users_with_scope_returns_mapped_list(client, db_session, as_principal):
    as_principal(scopes=["user:manage"])
    await _seed(db_session, email="a@example.com", role=UserRole.admin, display_name="Alice")
    await _seed(db_session, email="b@example.com", role=UserRole.user)
    r = await client.get(_USERS)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    emails = {u["email"] for u in body["data"]}
    assert emails == {"a@example.com", "b@example.com"}
    alice = next(u for u in body["data"] if u["email"] == "a@example.com")
    assert alice["role"] == "admin"
    assert alice["displayName"] == "Alice"
    assert alice["isActive"] is True


async def test_list_users_without_scope_403(client, as_principal):
    as_principal(role="user", scopes=_NO_MANAGE_SCOPES)
    r = await client.get(_USERS)
    assert r.status_code == 403


async def test_create_user_hashes_password_and_sets_role(client, db_session, as_principal):
    as_principal(scopes=["user:manage"])
    r = await client.post(_USERS, json={
        "email": "new@example.com", "role": "staff", "display_name": "New Person",
        "password": "secret123",
    })
    assert r.status_code == 201
    body = r.json()["user"]
    assert body["email"] == "new@example.com"
    assert body["role"] == "staff"
    stored = await user_repo.get_by_email(db_session, "new@example.com")
    assert stored is not None
    assert stored.password_hash != "secret123"


async def test_create_duplicate_email_conflict(client, db_session, as_principal):
    as_principal(scopes=["user:manage"])
    await _seed(db_session, email="dupe@example.com")
    r = await client.post(_USERS, json={"email": "dupe@example.com", "role": "user", "password": "x"})
    assert r.status_code == 409


async def test_get_user(client, db_session, as_principal):
    as_principal(scopes=["user:manage"])
    user = await _seed(db_session, email="g@example.com")
    r = await client.get(f"{_USERS}/{user.id}")
    assert r.status_code == 200
    assert r.json()["email"] == "g@example.com"


async def test_get_user_404(client, as_principal):
    as_principal(scopes=["user:manage"])
    r = await client.get(f"{_USERS}/00000000-0000-0000-0000-0000000000ff")
    assert r.status_code == 404


async def test_update_user_profile_and_role(client, db_session, as_principal):
    as_principal(scopes=["user:manage"])
    user = await _seed(db_session, email="u@example.com", role=UserRole.user, display_name="Old Name")
    r = await client.patch(f"{_USERS}/{user.id}", json={"display_name": "New Name", "role": "admin"})
    assert r.status_code == 200
    body = r.json()
    assert body["displayName"] == "New Name"
    assert body["role"] == "admin"


async def test_deactivate_then_activate(client, db_session, as_principal):
    as_principal(scopes=["user:manage"])
    user = await _seed(db_session, email="d@example.com")
    r = await client.post(f"{_USERS}/{user.id}/deactivate")
    assert r.status_code == 200 and r.json()["isActive"] is False
    r = await client.post(f"{_USERS}/{user.id}/activate")
    assert r.status_code == 200 and r.json()["isActive"] is True


async def test_deactivate_missing_user_404(client, as_principal):
    as_principal(scopes=["user:manage"])
    r = await client.post(f"{_USERS}/00000000-0000-0000-0000-0000000000ff/deactivate")
    assert r.status_code == 404


async def test_delete_user_removes_row(client, db_session, as_principal):
    as_principal(scopes=["user:manage"])
    user = await _seed(db_session, email="gone@example.com")
    r = await client.delete(f"{_USERS}/{user.id}")
    assert r.status_code == 204
    assert await user_repo.get(db_session, user.id) is None


async def test_delete_missing_user_404(client, as_principal):
    as_principal(scopes=["user:manage"])
    r = await client.delete(f"{_USERS}/00000000-0000-0000-0000-0000000000ff")
    assert r.status_code == 404


async def test_delete_own_account_forbidden(client, db_session, as_principal):
    user = await _seed(db_session, email="me@example.com", role=UserRole.admin)
    as_principal(sub=str(user.id), scopes=["user:manage"])
    r = await client.delete(f"{_USERS}/{user.id}")
    assert r.status_code == 403
    assert await user_repo.get(db_session, user.id) is not None
