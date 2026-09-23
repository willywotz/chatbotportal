from app.features.llm.services.purpose import KNOWN_PURPOSES, Purpose


def test_purpose_enum_has_exactly_five_members():
    assert [p.value for p in Purpose] == [
        "classification", "brief", "judge", "parse_spec", "popular_questions",
    ]


def test_known_purposes_matches_enum_values():
    assert KNOWN_PURPOSES == (
        "classification", "brief", "judge", "parse_spec", "popular_questions",
    )
