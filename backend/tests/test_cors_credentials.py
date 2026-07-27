from fastapi.testclient import TestClient

from app.main import app


def test_cors_allows_credentials_for_configured_origin():
    client = TestClient(app)
    r = client.options(
        "/api/v1/auth/login",
        headers={"Origin": "http://localhost:5173",
                 "Access-Control-Request-Method": "POST"},
    )
    assert r.headers.get("access-control-allow-credentials") == "true"
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
