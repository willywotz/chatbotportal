"""Access-control policy for the feedback-stats endpoint.

The handler no longer gates on admin: access is governed by the global role
allowlist (`enforce_role_allowlist`). Since the staff-role split, feedback-stats
is one of the six read-only ops dashboards reserved for `staff` (and `admin`) —
a plain `user` can no longer reach it. The aggregation query is Postgres-specific
and cannot run against the SQLite test DB, so the policy is asserted at the
allowlist layer that runs before any SQL.
"""

from app.auth.dependencies import _is_allowed_for_basic_user, _is_allowed_for_staff

_PATH = "/api/v1/feedback/statistics"


def test_feedback_stats_denied_for_basic_user():
    assert not _is_allowed_for_basic_user("GET", _PATH)


def test_feedback_stats_allowed_for_staff():
    assert _is_allowed_for_staff("GET", _PATH)
