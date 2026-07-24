from app.config import SETTINGS_GROUPS, settings


def test_onechat_base_url_default():
    assert settings.ONECHAT_BASE_URL == "http://185.84.160.55:8000"


def test_onechat_base_url_in_settings_group():
    assert "ONECHAT_BASE_URL" in SETTINGS_GROUPS["OneChat"]
