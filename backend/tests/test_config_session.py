from app.config import settings


def test_session_settings_defaults():
    assert settings.SESSION_COOKIE_NAME == "session_id"
    assert settings.AUTH_COOKIE_SECURE is True
    assert settings.SESSION_TTL_MINUTES == 60 * 24 * 7
    assert settings.SESSION_REFRESH_BELOW_MINUTES == 60 * 24 * 3
