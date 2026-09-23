"""The feedback-stats scalar assembly must survive an empty rating set.

The stats query is an ungrouped aggregate, so it returns one row even when no
message is rated — and in that state SQL AVG(...) is NULL, so `rate` (and the
up/down sums) come back as None. Assembling the response must coalesce those to
0 rather than crash on `None // 1`.
"""
from app.features.analytics.routers.feedback import _scalar_stats


def test_scalar_stats_coalesces_null_metrics():
    # Ungrouped aggregate over zero rated rows: one row, all metrics NULL.
    row = [{"total_rating": 0, "rating_up": None, "rating_down": None, "rate": None}]
    assert _scalar_stats(row) == (0, 0, 0, 0)


def test_scalar_stats_empty_result():
    assert _scalar_stats([]) == (0, 0, 0, 0)


def test_scalar_stats_preserves_real_values():
    row = [{"total_rating": 10, "rating_up": 7, "rating_down": 3, "rate": 70.0}]
    assert _scalar_stats(row) == (10, 7, 3, 70)
