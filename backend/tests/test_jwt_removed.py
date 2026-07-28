def test_jwt_helpers_are_gone():
    import app.auth.security as sec
    assert not hasattr(sec, "create_access_token")
    assert not hasattr(sec, "decode_access_token")


def test_jwt_settings_removed():
    from app.config import settings
    for name in ("JWT_SECRET", "JWT_ALGORITHM", "JWT_EXPIRE_MINUTES"):
        assert not hasattr(settings, name)
