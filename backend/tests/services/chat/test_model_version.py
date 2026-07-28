import pytest

from app.services.chat.model import resolve_model_version


@pytest.mark.parametrize("model,expected", [
    (None, "v5"),
    ("", "v5"),
    ("onechat", "v5"),
    ("ONECHAT", "v5"),
    ("onechat-v1", "v1"),
    ("onechat-v3", "v3"),
    ("onechat-v5", "v5"),
    ("onechat-v9", "v5"),   # unknown suffix -> lenient v5
    ("v3", "v5"),           # bare, not in the onechat- scheme -> v5
    ("garbage", "v5"),
])
def test_resolve_model_version(model, expected):
    assert resolve_model_version(model) == expected
