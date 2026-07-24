import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.parametrize("path", [
    "/api/v1/responses/resp_x/cancel",
    "/api/v1/responses/input_tokens",
    "/api/v1/responses/compact",
])
async def test_kind2_stubs_return_501(path, db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(path, json={"model": "thai-citizen-guide"})
        assert r.status_code == 501
        assert r.json()["error"]["code"] == "not_implemented"
        assert r.json()["error"]["type"] == "invalid_request_error"
