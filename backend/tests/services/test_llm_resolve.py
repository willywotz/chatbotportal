import pytest

from app.features.llm.services import resolve
from app.features.llm.services.errors import LlmError


@pytest.mark.asyncio
async def test_no_binding_is_config_error(db_session):
    resolve.invalidate()
    with pytest.raises(LlmError) as e:
        await resolve.for_purpose(db_session, "brief")
    assert e.value.kind == "config"


@pytest.mark.asyncio
async def test_resolves_with_fallback_chain(db_session, make_binding, set_fallback):
    primary = await make_binding("judge", model="a")
    fb = await make_binding("judge_fb", model="b")
    await set_fallback(primary, fb)
    resolve.invalidate()
    r = await resolve.for_purpose(db_session, "judge")
    assert r.model == "a"
    assert r.fallback is not None and r.fallback.model == "b"


@pytest.mark.asyncio
async def test_cycle_is_bounded(db_session, make_binding, set_fallback):
    a = await make_binding("p_a", model="a")
    b = await make_binding("p_b", model="b")
    await set_fallback(a, b)
    await set_fallback(b, a)
    resolve.invalidate()
    r = await resolve.for_purpose(db_session, "p_a")
    depth = 0
    node = r
    while node is not None:
        depth += 1
        node = node.fallback
    assert depth <= 3
