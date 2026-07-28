"""Re-rotate a near-expiry session cookie on any authenticated request.

Keeps an active browser's session sliding forward; idle sessions still expire.
Only session-cookie requests are touched — API-key/anonymous requests are not.
"""
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.services.auth_session import (
    create_session, expire_session, remaining_ttl, resolve_session,
)


class SessionRefreshMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        sid = request.cookies.get(settings.SESSION_COOKIE_NAME)
        response = await call_next(request)
        if not sid:
            return response
        ttl = await remaining_ttl(sid)
        if ttl is None or ttl >= settings.SESSION_REFRESH_BELOW_MINUTES * 60:
            return response
        user_id = await resolve_session(sid)
        if not user_id:
            return response
        new_sid = await create_session(user_id)
        # Grace instead of immediate delete: a sibling request already in
        # flight for the old sid must not spuriously 401.
        await expire_session(sid, settings.SESSION_ROTATE_GRACE_SECONDS)
        response.set_cookie(
            settings.SESSION_COOKIE_NAME, new_sid,
            httponly=True, secure=settings.AUTH_COOKIE_SECURE, samesite="Lax",
            max_age=settings.SESSION_TTL_MINUTES * 60, path="/",
        )
        return response
