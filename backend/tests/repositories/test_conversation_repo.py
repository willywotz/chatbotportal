import pytest

from app.models.user import User
from app.repositories import conversation as repo
from app.utils import now


@pytest.mark.asyncio
async def test_by_id_present_and_absent(db):
    c = await repo.create(title="t", agencies=[], status="active")
    assert (await repo.by_id(c.id)).id == c.id
    assert await repo.by_id("00000000-0000-0000-0000-000000000000") is None


@pytest.mark.asyncio
async def test_by_id_exclude_deleted(db):
    c = await repo.create(title="t", agencies=[], status="active", deleted_at=now())
    assert await repo.by_id(c.id) is not None                       # no filter → found
    assert await repo.by_id(c.id, exclude_deleted=True) is None      # filtered out


@pytest.mark.asyncio
async def test_list_and_count_filters_and_pages(db):
    u = await User.create(email="o@x.com", hashed_password="h", role="user")
    for i in range(3):
        await repo.create(title=f"keep {i}", agencies=[], status="active", user_id=u.id)
    await repo.create(title="other", agencies=[], status="active", user_id=u.id)
    rows, total = await repo.list_and_count(
        user_id=u.id, title_contains="keep", agency_contains=None,
        created_from=None, created_to=None, offset=0, limit=2)
    assert total == 3 and len(rows) == 2                             # total is pre-page count
    # Test agency_contains filter with JSON lookup
    tagged = await repo.create(title="tagged", agencies=["dga"], status="active", user_id=u.id)
    rows_a, total_a = await repo.list_and_count(
        user_id=u.id, title_contains=None, agency_contains="dga",
        created_from=None, created_to=None, offset=None, limit=None)
    assert total_a == 1 and [r.id for r in rows_a] == [tagged.id]    # only tagged row matches


@pytest.mark.asyncio
async def test_save_partial_and_delete(db):
    c = await repo.create(title="t", agencies=[], status="active")
    c.external_session_id = "sess-1"
    await repo.save(c, update_fields=["external_session_id"])
    assert (await repo.by_id(c.id)).external_session_id == "sess-1"
    await repo.delete(c)
    assert await repo.by_id(c.id) is None
