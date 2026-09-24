import pytest
from app.features.llm.services import usage


class _Repo:
    def __init__(self):
        self.rows = []

    async def create(self, session, **kw):
        self.rows.append(kw)


@pytest.mark.asyncio
async def test_record_one_model(monkeypatch):
    repo = _Repo()
    monkeypatch.setattr(usage, "llm_usage_repo", repo)
    await usage.record(None, {"gpt-4o-mini": {"input_tokens": 5, "output_tokens": 7}},
                       purpose="brief")
    assert repo.rows[0]["model"] == "gpt-4o-mini"
    assert repo.rows[0]["prompt_tokens"] == 5
    assert repo.rows[0]["completion_tokens"] == 7


@pytest.mark.asyncio
async def test_record_empty_is_noop(monkeypatch):
    repo = _Repo()
    monkeypatch.setattr(usage, "llm_usage_repo", repo)
    await usage.record(None, {}, purpose="brief")
    assert repo.rows == []


@pytest.mark.asyncio
async def test_record_swallows_errors(monkeypatch):
    class Boom:
        async def create(self, *a, **k):
            raise RuntimeError("db down")
    monkeypatch.setattr(usage, "llm_usage_repo", Boom())
    await usage.record(None, {"m": {"input_tokens": 1, "output_tokens": 1}}, purpose="brief")
