"""The /api/v1/public/ namespace must be auth-optional for every role/method.

A `user`-role token posting to /api/v1/public/chat (or GETting a public
agency logo) must not be 403'd by the role allowlist chokepoint — only the
old exact "/api/v1/chat" string is in the `user` write allowlist, so without
an explicit passthrough the new /public/chat path would 403 an authenticated
guest. See app/auth/dependencies.py::enforce_role_allowlist.
"""
from starlette.requests import Request


def _request(method: str, path: str, *, token: str | None = None) -> Request:
    headers = [(b"authorization", f"Bearer {token}".encode())] if token else []
    return Request({"type": "http", "method": method, "path": path, "headers": headers})


async def test_user_token_posts_to_public_chat_without_403(db, make_token):
    from app.auth.dependencies import enforce_role_allowlist

    token = make_token(role="user")
    assert await enforce_role_allowlist(_request("POST", "/api/v1/public/chat", token=token)) is None


async def test_user_token_gets_public_agency_logo_without_403(db, make_token):
    from app.auth.dependencies import enforce_role_allowlist

    token = make_token(role="user")
    path = "/api/v1/public/agencies/abc-123/logo"
    assert await enforce_role_allowlist(_request("GET", path, token=token)) is None
