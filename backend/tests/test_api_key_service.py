"""Tests for app.services.api_key — data access moved out of the router."""

from app.errors import ApiError
from app.models.user import User, UserAPIKey
from app.services import api_key as api_key_service


async def _user(email="svc@x.com"):
    return await User.create(email=email, hashed_password="h")


async def test_create_returns_key_and_raw_value(db):
    user = await _user()
    key, raw = await api_key_service.create(user.id, "n", None)
    assert raw.startswith("tcg_")
    assert key.expires_at is None
    stored = await UserAPIKey.get(id=key.id)
    assert stored.key_prefix == raw[:12]


async def test_create_rejects_non_positive_expiry(db):
    user = await _user()
    try:
        await api_key_service.create(user.id, "n", 0)
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status == 400


async def test_list_for_user_scopes_by_owner(db):
    owner = await _user("owner@x.com")
    other = await _user("other@x.com")
    await api_key_service.create(owner.id, "n1", None)
    await api_key_service.create(other.id, "n2", None)
    rows = await api_key_service.list_for_user(owner.id)
    assert len(rows) == 1
    assert rows[0].user_id == owner.id


async def test_rename_updates_name(db):
    user = await _user()
    key, _ = await api_key_service.create(user.id, "old", None)
    renamed = await api_key_service.rename(key.id, user.id, "new")
    assert renamed.name == "new"


async def test_rename_other_owner_raises_404(db):
    owner = await _user("owner2@x.com")
    other = await _user("other2@x.com")
    key, _ = await api_key_service.create(owner.id, "n", None)
    try:
        await api_key_service.rename(key.id, other.id, "new")
        raise AssertionError("expected ApiError")
    except ApiError as exc:
        assert exc.status == 404


async def test_delete_removes_row(db):
    user = await _user()
    key, _ = await api_key_service.create(user.id, "n", None)
    await api_key_service.delete(key.id, user.id)
    assert await UserAPIKey.filter(id=key.id).count() == 0


async def test_revoke_sets_revoked_at_once(db):
    user = await _user()
    key, _ = await api_key_service.create(user.id, "n", None)
    revoked = await api_key_service.revoke(key.id, user.id)
    assert revoked.revoked_at is not None
    revoked_again = await api_key_service.revoke(key.id, user.id)
    assert revoked_again.revoked_at == revoked.revoked_at
