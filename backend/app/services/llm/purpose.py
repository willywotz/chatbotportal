from enum import StrEnum


class Purpose(StrEnum):
    CLASSIFICATION = "classification"
    BRIEF = "brief"
    JUDGE = "judge"
    PARSE_SPEC = "parse_spec"
    POPULAR_QUESTIONS = "popular_questions"


# Serialized string values, kept for the /language-model/purposes endpoint and any list use.
KNOWN_PURPOSES = tuple(p.value for p in Purpose)
