"""POST /agencies/parse-specification must translate LlmError provider failures into HTTP 502.

`parse_spec` was migrated to the new LLM client and now raises `LlmError` on
provider failure instead of `httpx` errors. The endpoint must not let that
exception escape as an unhandled 500.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.features.agency.routers.spec as spec_mod
from app.core.security.dependencies import get_current_user
from app.features.agency.routers import router
from app.features.llm.services import LlmError

_PATH = "/api/v1/agencies/parse-specification"


async def _raising_parse_spec(_spec_text: str) -> dict:
    raise LlmError("boom")


def _app(monkeypatch, principal) -> FastAPI:
    monkeypatch.setattr(spec_mod, "parse_spec", _raising_parse_spec)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: principal
    return app


def test_parse_spec_translates_llm_error_to_502(monkeypatch, as_principal):
    r = TestClient(_app(monkeypatch, as_principal())).post(_PATH, json={"spec_text": "openapi: 3.0.0"})
    assert r.status_code == 502
    assert "LLM provider error" in r.json()["detail"]
