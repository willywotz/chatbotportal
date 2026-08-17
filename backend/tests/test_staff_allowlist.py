"""The staff allowlist = basic-user allowlist + the six read-only dashboards."""
from app.auth.dependencies import (
    _STAFF_GET_EXACT,
    _is_allowed_for_basic_user,
    _is_allowed_for_staff,
)

_DASHBOARDS = [
    "/api/v1/dashboard/stats",
    "/api/v1/executive-summary",
    "/api/v1/agency-health",
    "/api/v1/usage-heatmap",
    "/api/v1/insight/usage",
    "/api/v1/feedback/stats",
]


def test_staff_reads_all_six_dashboards():
    for path in _DASHBOARDS:
        assert _is_allowed_for_staff("GET", path)


def test_staff_get_exact_is_exactly_the_six_dashboards():
    assert _STAFF_GET_EXACT == frozenset(_DASHBOARDS)


def test_staff_keeps_everything_a_basic_user_can_do():
    shared = [
        ("POST", "/api/v1/chat"),
        ("POST", "/api/v1/responses"),
        ("PATCH", "/api/v1/messages/abc-123/rating"),
        ("GET", "/api/v1/history"),
        ("DELETE", "/api/v1/history/abc-123"),
        ("GET", "/api/v1/history/abc-123/messages"),
        ("GET", "/api/v1/agencies"),
        ("GET", "/api/v1/authentication/me"),
    ]
    for method, path in shared:
        assert _is_allowed_for_basic_user(method, path)
        assert _is_allowed_for_staff(method, path)


def test_staff_still_cannot_reach_admin_surface():
    for method, path in [
        ("GET", "/api/v1/connection-logs"),
        ("GET", "/api/v1/api-keys/"),
        ("POST", "/api/v1/executive-summary/regenerate"),
        ("DELETE", "/api/v1/agencies/abc-123"),
    ]:
        assert not _is_allowed_for_staff(method, path)


# The pre-split `user` reachable surface (representative (method, path) pairs),
# captured from the two-role model. `staff` must reach all of these.
_PRE_SPLIT_USER_SURFACE = [
    ("POST", "/api/v1/chat"),
    ("POST", "/api/v1/responses"),
    ("PATCH", "/api/v1/messages/abc-123/rating"),
    ("GET", "/api/v1/history"),
    ("DELETE", "/api/v1/history/abc-123"),
    ("GET", "/api/v1/history/abc-123/messages"),
    ("GET", "/api/v1/agencies"),
    ("GET", "/api/v1/authentication/me"),
    ("GET", "/api/v1/dashboard/stats"),
    ("GET", "/api/v1/executive-summary"),
    ("GET", "/api/v1/agency-health"),
    ("GET", "/api/v1/usage-heatmap"),
    ("GET", "/api/v1/insight/usage"),
    ("GET", "/api/v1/feedback/stats"),
]


def test_staff_surface_equals_pre_split_user_surface():
    for method, path in _PRE_SPLIT_USER_SURFACE:
        assert _is_allowed_for_staff(method, path), f"staff lost {method} {path}"


def test_user_surface_is_staff_minus_the_dashboards():
    for method, path in _PRE_SPLIT_USER_SURFACE:
        if (method, path) in [("GET", p) for p in _DASHBOARDS]:
            assert not _is_allowed_for_basic_user(method, path), f"user kept dashboard {path}"
        else:
            assert _is_allowed_for_basic_user(method, path), f"user lost {method} {path}"
