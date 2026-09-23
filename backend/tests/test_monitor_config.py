from app.core.config import Settings


def test_monitor_defaults_present():
    s = Settings()
    assert s.MONITOR_TICK_SECONDS == 15
    assert s.MONITOR_CLAIM_BATCH == 50
    assert s.MONITOR_PROBE_CONCURRENCY == 5
    assert s.DEFAULT_CHECK_INTERVAL_SECONDS == 300
    assert s.CHECK_JITTER_SECONDS == 30
    assert s.CHECK_RETRY_MAX == 3
    assert s.CHECK_BACKOFF_BASE_MS == 200
    assert s.FAILURE_THRESHOLD == 3
    assert s.UPTIME_BUCKET_HOUR_RETENTION_DAYS == 14
    assert s.UPTIME_BUCKET_DAY_RETENTION_DAYS == 365
