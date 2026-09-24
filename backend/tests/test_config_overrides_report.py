import logging

from app.core.config import Settings


def test_apply_overrides_reports_unknown_and_invalid(caplog):
    s = Settings()
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        report = s.apply_overrides({
            "LLM_CALL_TIMEOUT": "42",
            "NOPE_KEY": "x",
            "TITLE_MAX_LENGTH": "abc",
        })
    assert s.LLM_CALL_TIMEOUT == 42
    assert report.applied == ["LLM_CALL_TIMEOUT"]
    assert report.unknown == ["NOPE_KEY"]
    assert report.invalid == ["TITLE_MAX_LENGTH"]
    assert any("NOPE_KEY" in r.getMessage() for r in caplog.records)
