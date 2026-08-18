import pytest

from app.repositories import agency as repo


async def _mk(name, **kw):
    return await repo.create(name=name, **kw)


@pytest.mark.asyncio
async def test_by_id_present_and_absent(db):
    a = await _mk("DGA", status="active")
    assert (await repo.by_id(a.id)).id == a.id
    assert await repo.by_id("00000000-0000-0000-0000-000000000000") is None


@pytest.mark.asyncio
async def test_list_and_count_filters(db):
    await _mk("Active One", status="active", connection_type="API")
    await _mk("Draft One", status="draft", connection_type="MCP")
    rows, total = await repo.list_and_count(status="all", connection_type=None, search_text=None)
    assert total == 2 and len(rows) == 2
    rows, total = await repo.list_and_count(status="active", connection_type=None, search_text=None)
    assert total == 1 and rows[0].name == "Active One"
    rows, total = await repo.list_and_count(status="all", connection_type="api", search_text=None)
    assert total == 1 and rows[0].connection_type == "API"          # .upper() applied
    rows, total = await repo.list_and_count(status="all", connection_type=None, search_text="draft")
    assert total == 1 and rows[0].name == "Draft One"


@pytest.mark.asyncio
async def test_increment_calls_is_atomic_and_refreshes(db):
    a = await _mk("Counter", status="active", total_calls=5)
    returned = await repo.increment_calls(a)
    assert returned.total_calls == 6                                # in-memory refreshed
    assert (await repo.by_id(a.id)).total_calls == 6                # persisted
    await repo.increment_calls(a)
    assert (await repo.by_id(a.id)).total_calls == 7


@pytest.mark.asyncio
async def test_save_partial_delete_count(db):
    a = await _mk("S", status="active", rating_up=0)
    a.rating_up = 3
    await repo.save(a, update_fields=["rating_up"])
    assert (await repo.by_id(a.id)).rating_up == 3
    assert await repo.count_all() == 1
    await repo.delete(a)
    assert await repo.by_id(a.id) is None
    assert await repo.count_all() == 0
