"""CHAT_STREAM_VERSION selects which OneChat upstream the SSE proxy calls.

Defaults to v5; "v4" is the no-redeploy rollback; anything else falls back to
v5 rather than calling a bogus URL.
"""

import pytest

from app.config import settings
from app.routers.chat import _stream_version


@pytest.fixture
def restore_version():
    original = settings.CHAT_STREAM_VERSION
    yield
    settings.CHAT_STREAM_VERSION = original


def test_default_is_v5():
    assert settings.CHAT_STREAM_VERSION == "v5"
    assert _stream_version() == "v5"


def test_v4_selects_v4(restore_version):
    settings.CHAT_STREAM_VERSION = "v4"
    assert _stream_version() == "v4"


def test_case_and_whitespace_tolerant(restore_version):
    settings.CHAT_STREAM_VERSION = " V4 "
    assert _stream_version() == "v4"


def test_unknown_value_falls_back_to_v5(restore_version):
    settings.CHAT_STREAM_VERSION = "v9"
    assert _stream_version() == "v5"


def test_v5_url_is_registered_in_settings_group():
    from app.config import SETTINGS_GROUPS

    assert "ONECHAT_BASE_URL" in SETTINGS_GROUPS["OneChat"]
    assert "ONECHAT_V5_URL" not in SETTINGS_GROUPS["OneChat"]
    assert "CHAT_STREAM_VERSION" in SETTINGS_GROUPS["OneChat"]
