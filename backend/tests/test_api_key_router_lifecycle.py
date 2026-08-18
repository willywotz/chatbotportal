from app.models.user import User, UserAPIKey
from app.routers.api_key import (
    CreateAPIKeyRequest, create_api_key, list_api_keys, revoke_api_key,
)


async def test_create_with_expiry(db):
    user = await User.create(email="c@x.com", hashed_password="h")
    resp = await create_api_key(
        CreateAPIKeyRequest(name="n", expires_in_days=30), user=user
    )
    assert resp.key.startswith("tcg_")
    assert resp.expires_at is not None
    assert resp.status == "active"
    key = await UserAPIKey.get(id=resp.id)
    assert key.expires_at is not None


async def test_create_without_options_never_expires(db):
    user = await User.create(email="c2@x.com", hashed_password="h")
    resp = await create_api_key(CreateAPIKeyRequest(name="n"), user=user)
    assert resp.expires_at is None
    assert resp.status == "active"


async def test_revoke_sets_status_revoked(db):
    user = await User.create(email="r@x.com", hashed_password="h")
    created = await create_api_key(CreateAPIKeyRequest(name="n"), user=user)
    revoked = await revoke_api_key(created.id, user=user)
    assert revoked.status == "revoked"
    key = await UserAPIKey.get(id=created.id)
    assert key.revoked_at is not None


async def test_revoke_other_users_key_404(db):
    owner = await User.create(email="o@x.com", hashed_password="h")
    other = await User.create(email="x@x.com", hashed_password="h")
    created = await create_api_key(CreateAPIKeyRequest(name="n"), user=owner)
    import pytest
    from app.errors import ApiError
    with pytest.raises(ApiError) as e:
        await revoke_api_key(created.id, user=other)
    assert e.value.status == 404


async def test_list_includes_status(db):
    user = await User.create(email="l@x.com", hashed_password="h")
    await create_api_key(CreateAPIKeyRequest(name="n"), user=user)
    rows = await list_api_keys(user=user)
    assert rows[0].status == "active"
