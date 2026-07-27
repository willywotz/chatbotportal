from app.config import SETTINGS_GROUPS, Settings


def test_llm_provider_settings_not_editable_via_generic_ui():
    flat = {k for v in SETTINGS_GROUPS.values() for k in v}
    for key in ("OPENROUTER_API_KEY", "OPENROUTER_API_URL", "CLASSIFICATION_MODEL",
                "PARSE_SPEC_URL", "PARSE_SPEC_API_KEY", "PARSE_SPEC_LLM_MODEL"):
        assert key not in flat


def test_removed_setting_groups_are_gone():
    for group in ("Database", "CORS", "Auth", "Analytics", "Executive summary", "Quota"):
        assert group not in SETTINGS_GROUPS


def test_similarity_group_is_first():
    assert next(iter(SETTINGS_GROUPS)) == "Similarity"


def test_permissive_defaults():
    s = Settings()
    assert s.CORS_ORIGINS == ["http://localhost:5173", "http://localhost:8080"]
    assert s.WEEKLY_BRIEF_TIMEOUT >= 3600.0         # effectively no limit
