"""The last active admin cannot be demoted away from the admin role."""
import pytest

from app.errors import ApiError
from app.models.user import User
from app.services import user as user_service


async def test_ensure_not_last_admin_raises_for_sole_admin(db):
    admin = await User.create(email="sole-admin@x.com", hashed_password="h", role="admin")
    with pytest.raises(ApiError) as e:
        await user_service.ensure_not_last_admin(admin)
    assert e.value.status == 400


async def test_ensure_not_last_admin_ok_with_a_second_admin(db):
    a = await User.create(email="admin-a@x.com", hashed_password="h", role="admin")
    await User.create(email="admin-b@x.com", hashed_password="h", role="admin")
    assert await user_service.ensure_not_last_admin(a) is None


async def test_ensure_not_last_admin_ignores_non_admin_target(db):
    viewer = await User.create(email="v@x.com", hashed_password="h", role="viewer")
    # Not an admin → never the "last admin", returns without raising.
    assert await user_service.ensure_not_last_admin(viewer) is None
