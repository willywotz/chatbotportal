"""WebSocket caller resolution + Origin check.

Same precedence as the HTTP path (header API-key decides; else session cookie).
The Origin check is the standard cross-site-WebSocket-hijacking defense — cookies
now authenticate sockets, so a browser page from another origin must not be able
to open an authenticated socket (SameSite=Lax already blocks the cookie; this is
defense-in-depth).
"""
from urllib.parse import urlparse

from app.auth.dependencies import _resolve_api_key
from app.config import settings
from app.models.user import User
from app.services.auth_session import resolve_session


async def resolve_ws_user(websocket) -> User | None:
    auth = websocket.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return await _resolve_api_key(auth[7:])
    sid = websocket.cookies.get(settings.SESSION_COOKIE_NAME)
    if sid:
        user_id = await resolve_session(sid)
        if user_id:
            return await User.filter(id=user_id, is_active=True).first()
    return None


def ws_origin_allowed(websocket) -> bool:
    origin = websocket.headers.get("origin")
    if origin is None:
        return False
    allowed = settings.CORS_ORIGINS
    if "*" in allowed:
        return True
    if origin in allowed:
        return True
    # Same-origin: the Origin's host:port equals the Host the browser addressed.
    # Always legitimate; a cross-site page would send Origin != Host.
    host = websocket.headers.get("host")
    return bool(host) and urlparse(origin).netloc == host
