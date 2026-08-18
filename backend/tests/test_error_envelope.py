from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.errors import ApiError, ErrorCode, register_error_handlers


def _app():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/api/v1/boom")
    async def boom():
        raise ApiError("agency_timeout", "Agency X timed out", status=504, retryable=True)

    @app.get("/api/v1/http")
    async def http():
        raise HTTPException(status_code=404, detail="Not found")

    @app.get("/api/v1/conflict")
    async def conflict():
        raise ApiError(ErrorCode.CONFLICT, "x", status=409)

    @app.get("/api/v1/http-conflict")
    async def http_conflict():
        raise HTTPException(status_code=409, detail="x")

    return app


def test_api_error_envelope():
    r = TestClient(_app()).get("/api/v1/boom")
    assert r.status_code == 504
    assert r.json() == {
        "error": {"code": "agency_timeout", "message": "Agency X timed out", "retryable": True}
    }


def test_http_exception_mapped_to_envelope():
    r = TestClient(_app()).get("/api/v1/http")
    assert r.status_code == 404
    body = r.json()["error"]
    assert body["code"] == "not_found" and body["message"] == "Not found"


def test_api_error_conflict_envelope():
    r = TestClient(_app()).get("/api/v1/conflict")
    assert r.status_code == 409
    assert r.json() == {"error": {"code": "conflict", "message": "x", "retryable": False}}


def test_http_exception_conflict_mapped_to_envelope():
    r = TestClient(_app()).get("/api/v1/http-conflict")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


def test_unmatched_route_uses_envelope():
    app = FastAPI()
    register_error_handlers(app)
    r = TestClient(app).get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    assert r.json()["error"]["message"]  # non-empty
