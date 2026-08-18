"""POST /agencies/parse-specification must require authentication (it invokes an LLM).

Both tests mock `parse_spec`, so any 401/403 can only come from our auth layer —
never from the upstream LLM rejecting the gateway's key (which would mean the
anonymous request already reached and paid for the LLM call).
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers.agencies.spec as spec_mod
from app.auth.dependencies import get_current_user
from app.routers.agencies import router

_PATH = "/api/v1/agencies/parse-specification"


async def _fake_parse_spec(_spec_text: str) -> dict:
    return {"name": "X", "endpoints": []}


def _app(monkeypatch) -> FastAPI:
    monkeypatch.setattr(spec_mod, "parse_spec", _fake_parse_spec)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def test_parse_spec_rejects_anonymous(monkeypatch):
    # parse_spec is mocked, so the only way to get 401/403 is our auth layer
    # rejecting the request before the handler runs.
    r = TestClient(_app(monkeypatch)).post(_PATH, json={"spec_text": "openapi: 3.0.0"})
    assert r.status_code in (401, 403)


def test_parse_spec_allows_authenticated(monkeypatch):
    app = _app(monkeypatch)
    app.dependency_overrides[get_current_user] = lambda: object()
    r = TestClient(app).post(_PATH, json={"spec_text": "openapi: 3.0.0"})
    assert r.status_code == 200
    assert r.json() == {"success": True, "data": {"name": "X", "endpoints": []}}
