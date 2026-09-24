import pytest

from app.features.llm.repositories import llm as repo


@pytest.mark.asyncio
async def test_create_and_get_provider(db_session):
    p = await repo.create_provider(db_session, name="p0", provider="openai",
                                   model="gpt-4o-mini", api_key="k")
    got = await repo.get_provider(db_session, p.id)
    assert got is not None and got.name == "p0"
    by_name = await repo.get_provider_by_name(db_session, "p0")
    assert by_name is not None and by_name.id == p.id


@pytest.mark.asyncio
async def test_enabled_binding_for_purpose(db_session):
    p = await repo.create_provider(db_session, name="p1", provider="openai",
                                   model="gpt-4o-mini", api_key="k")
    await repo.create_binding(db_session, purpose="brief", provider_id=p.id)
    got = await repo.enabled_binding_for_purpose(db_session, "brief")
    assert got is not None and got.provider_id == p.id


@pytest.mark.asyncio
async def test_binding_purpose_exists(db_session):
    p = await repo.create_provider(db_session, name="p3", provider="openai",
                                   model="m", api_key="k")
    b = await repo.create_binding(db_session, purpose="classification", provider_id=p.id)
    assert await repo.binding_purpose_exists(db_session, "classification") is True
    assert await repo.binding_purpose_exists(
        db_session, "classification", exclude_id=b.id) is False
    assert await repo.binding_purpose_exists(db_session, "nope") is False


@pytest.mark.asyncio
async def test_provider_has_bindings_guard(db_session):
    p = await repo.create_provider(db_session, name="p2", provider="openai",
                                   model="m", api_key="k")
    await repo.create_binding(db_session, purpose="judge", provider_id=p.id)
    assert await repo.provider_has_bindings(db_session, p.id) is True


@pytest.mark.asyncio
async def test_update_and_delete_binding(db_session):
    p = await repo.create_provider(db_session, name="p4", provider="openai",
                                   model="m", api_key="k")
    b = await repo.create_binding(db_session, purpose="parse_spec", provider_id=p.id)
    await repo.update_binding(db_session, b, {"model_override": "gpt-4o"})
    assert (await repo.get_binding(db_session, b.id)).model_override == "gpt-4o"
    assert await repo.get_binding_by_purpose(db_session, "parse_spec") is not None
    await repo.delete_binding(db_session, b)
    await db_session.flush()
    assert await repo.get_binding_by_purpose(db_session, "parse_spec") is None
