from fastapi.testclient import TestClient

from app.main import app


def test_cors_reflects_any_origin_with_credentials():
    client = TestClient(app)
    r = client.options(
        "/api/v1/authentication/login",
        headers={"Origin": "http://anything.example",
                 "Access-Control-Request-Method": "POST"},
    )
    assert r.headers.get("access-control-allow-credentials") == "true"
    assert r.headers.get("access-control-allow-origin") == "http://anything.example"
