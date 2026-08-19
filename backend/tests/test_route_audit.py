from app.main import app
from app.auth.dependencies import require_scope

_WHITELIST_EXACT = {("GET", "/api/v1/authentication/me")}
_WHITELIST_PREFIX = ("/api/v1/agent-proxy/",)  # external OneChat callback, own auth


def _uses_require_scope(route) -> bool:
    for dep in getattr(route.dependant, "dependencies", []):
        if getattr(dep, "call", None) is require_scope:
            return True
    return False


def test_every_api_route_is_classified():
    offenders = []
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if not path.startswith("/api/v1/"):
            continue
        if path.startswith("/api/v1/public/"):
            continue
        if any(path.startswith(p) for p in _WHITELIST_PREFIX):
            continue
        for m in methods:
            if (m, path) in _WHITELIST_EXACT:
                continue
            if not _uses_require_scope(route):
                offenders.append(f"{m} {path}")
    assert not offenders, f"unclassified routes: {sorted(set(offenders))}"
