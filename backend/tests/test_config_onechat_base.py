from app.config import SETTINGS_GROUPS, settings


def test_onechat_base_url_default():
    assert settings.ONECHAT_BASE_URL == "http://185.84.160.55:8000"


def test_onechat_base_url_in_settings_group():
    assert "ONECHAT_BASE_URL" in SETTINGS_GROUPS["OneChat"]


def test_legacy_onechat_urls_removed():
    from app import config
    assert not hasattr(config.settings, "ONECHAT_V3_URL")
    assert "ONECHAT_V3_URL" not in config.SETTINGS_GROUPS["OneChat"]
    assert config.SETTINGS_GROUPS["OneChat"] == [
        "CHAT_STREAM_VERSION", "MCP_ENDPOINT_URL", "ONECHAT_BASE_URL",
    ]
