from app.core.config import settings
from app.features.chat.services.dispatch import _dispatch_timeout


def test_dispatch_timeout_prefers_per_agency():
    assert _dispatch_timeout({"dispatch_timeout_s": 45}) == 45


def test_dispatch_timeout_falls_back_to_global():
    assert _dispatch_timeout({"dispatch_timeout_s": None}) == settings.AGENCY_CHAT_TIMEOUT
    assert _dispatch_timeout({}) == settings.AGENCY_CHAT_TIMEOUT
