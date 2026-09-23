from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.features.llm.models.llm_usage import LlmUsage
from app.features.llm.repositories import llm as llm_repo
from app.features.llm.services import client as c

pytestmark = pytest.mark.asyncio


def _mock_httpx(json_body, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_body
    resp.text = "body"
    client = MagicMock()
    client.post = AsyncMock(return_value=resp)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm), client


async def _usage_count(session, purpose: str) -> int:
    rows = (await session.execute(select(LlmUsage).where(LlmUsage.purpose == purpose))).scalars().all()
    return len(rows)


async def test_client_chat_is_transport_only(db_session):
    c.invalidate()
    p = await llm_repo.create_provider(
        db_session, name="openrouter", base_url="https://api/x", api_key="sk",
        auth_header="Authorization", auth_scheme="Bearer", request_usage=True,
    )
    await llm_repo.create_route(db_session, purpose="classification", provider_id=p.id, model="m1")
    body = {"model": "m1", "choices": [{"message": {"content": "hi", "tool_calls": None}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "cost": 0.001}}
    factory, client = _mock_httpx(body)
    with patch.object(c.httpx, "AsyncClient", factory):
        res = await c.chat(db_session, purpose="classification", messages=[{"role": "user", "content": "x"}])
    assert res.content == "hi"
    _, kwargs = client.post.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer sk"
    assert kwargs["json"]["usage"] == {"include": True}
    assert await _usage_count(db_session, "classification") == 0  # transport records nothing


async def test_package_chat_records_usage(db_session):
    from app.features.llm.services import chat as pkg_chat
    c.invalidate()
    p = await llm_repo.create_provider(
        db_session, name="openrouter", base_url="https://api/x", api_key="sk",
        auth_header="Authorization", auth_scheme="Bearer", request_usage=True,
    )
    await llm_repo.create_route(db_session, purpose="classification", provider_id=p.id, model="m1")
    body = {"model": "m1", "choices": [{"message": {"content": "hi", "tool_calls": None}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "cost": 0.001}}
    factory, _ = _mock_httpx(body)
    with patch.object(c.httpx, "AsyncClient", factory):
        res = await pkg_chat(db_session, purpose="classification", messages=[{"role": "user", "content": "x"}])
    assert res.content == "hi"
    assert await _usage_count(db_session, "classification") == 1


async def test_chat_non_2xx_raises_llmerror(db_session):
    c.invalidate()
    p = await llm_repo.create_provider(db_session, name="p", base_url="u", api_key="k")
    await llm_repo.create_route(db_session, purpose="judge", provider_id=p.id, model="m")
    factory, _ = _mock_httpx({"error": "x"}, status=500)
    with patch.object(c.httpx, "AsyncClient", factory):
        with pytest.raises(c.LlmError) as e:
            await c.chat(db_session, purpose="judge", messages=[])
    assert e.value.status == 500


async def test_chat_passes_max_tokens(db_session):
    c.invalidate()
    p = await llm_repo.create_provider(db_session, name="p", base_url="u", api_key="k")
    await llm_repo.create_route(db_session, purpose="brief", provider_id=p.id, model="m")
    body = {"model": "m", "choices": [{"message": {"content": "hi"}}]}
    factory, client = _mock_httpx(body)
    with patch.object(c.httpx, "AsyncClient", factory):
        await c.chat(db_session, purpose="brief", messages=[], max_tokens=1)
    _, kwargs = client.post.call_args
    assert kwargs["json"]["max_tokens"] == 1


async def test_ping_ok_reports_latency_and_model(db_session):
    c.invalidate()
    p = await llm_repo.create_provider(db_session, name="p", base_url="u", api_key="k")
    await llm_repo.create_route(db_session, purpose="classification", provider_id=p.id, model="m1")
    body = {"model": "m1", "choices": [{"message": {"content": "pong"}}]}
    factory, _ = _mock_httpx(body)
    with patch.object(c.httpx, "AsyncClient", factory):
        res = await c.ping(db_session, "classification")
    assert res.ok is True
    assert res.model == "m1"
    assert res.latency_ms >= 0
    assert res.error is None


async def test_ping_disabled_route_reports_error(db_session):
    c.invalidate()
    p = await llm_repo.create_provider(db_session, name="p", base_url="u", api_key="k")
    await llm_repo.create_route(db_session, purpose="judge", provider_id=p.id, model="m", enabled=False)
    res = await c.ping(db_session, "judge")
    assert res.ok is False
    assert res.model is None
    assert "no enabled route" in res.error


async def test_ping_records_no_usage(db_session):
    c.invalidate()
    p = await llm_repo.create_provider(db_session, name="p", base_url="u", api_key="k")
    await llm_repo.create_route(db_session, purpose="classification", provider_id=p.id, model="m1")
    body = {"model": "m1", "choices": [{"message": {"content": "pong"}}]}
    factory, _ = _mock_httpx(body)
    with patch.object(c.httpx, "AsyncClient", factory):
        await c.ping(db_session, "classification")
    assert await _usage_count(db_session, "classification") == 0
