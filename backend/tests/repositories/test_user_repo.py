import pytest

from app.repositories import user as repo


async def _mk(email, **kw):
    return await repo.create(email=email, hashed_password="h", **kw)


@pytest.mark.asyncio
async def test_by_id_present_and_absent(db):
    u = await _mk("a@x.com", role="user")
    assert (await repo.by_id(u.id)).id == u.id
    assert await repo.by_id("00000000-0000-0000-0000-000000000000") is None


@pytest.mark.asyncio
async def test_active_lookups_skip_inactive(db):
    active = await _mk("live@x.com", role="user", is_active=True)
    await _mk("dead@x.com", role="user", is_active=False)
    assert (await repo.active_by_id(active.id)).id == active.id
    assert (await repo.active_by_email("live@x.com")).id == active.id
    assert await repo.active_by_email("dead@x.com") is None


@pytest.mark.asyncio
async def test_email_exists_and_count_all(db):
    await _mk("one@x.com", role="user")
    assert await repo.email_exists("one@x.com") is True
    assert await repo.email_exists("missing@x.com") is False
    assert await repo.count_all() == 1


@pytest.mark.asyncio
async def test_count_other_active_admins_excludes_self(db):
    a1 = await _mk("admin1@x.com", role="admin", is_active=True)
    await _mk("admin2@x.com", role="admin", is_active=True)
    await _mk("inactive-admin@x.com", role="admin", is_active=False)
    assert await repo.count_other_active_admins(a1.id) == 1     # admin2 only


@pytest.mark.asyncio
async def test_search_filters(db):
    await _mk("alice@x.com", role="admin", is_active=True, display_name="Alice")
    await _mk("bob@x.com", role="user", is_active=False, display_name="Bob")
    await _mk("anon@ephemeral.local", role="user", is_active=True, is_ephemeral=True)
    all_rows = await repo.search(search_text=None, role=None, is_active=None)
    assert {u.email for u in all_rows} == {"alice@x.com", "bob@x.com"}   # ephemeral excluded
    admins = await repo.search(search_text=None, role="admin", is_active=None)
    assert [u.email for u in admins] == ["alice@x.com"]
    hits = await repo.search(search_text="ali", role=None, is_active=None)
    assert [u.email for u in hits] == ["alice@x.com"]


@pytest.mark.asyncio
async def test_save_partial(db):
    u = await _mk("s@x.com", role="user", is_active=True)
    u.is_active = False
    await repo.save(u, update_fields=["is_active"])
    assert (await repo.by_id(u.id)).is_active is False
