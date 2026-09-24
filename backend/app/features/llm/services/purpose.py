from enum import StrEnum

from pydantic import BaseModel

from app.features.llm.services.result_schemas import (
    ClassificationResult, JudgeResult, PopularQuestionsResult, SpecResult,
)


class Purpose(StrEnum):
    CLASSIFICATION = "classification"
    BRIEF = "brief"
    JUDGE = "judge"
    PARSE_SPEC = "parse_spec"
    POPULAR_QUESTIONS = "popular_questions"


KNOWN_PURPOSES = tuple(p.value for p in Purpose)

PURPOSE_SCHEMAS: dict[Purpose, type[BaseModel] | None] = {
    Purpose.CLASSIFICATION: ClassificationResult,
    Purpose.BRIEF: None,
    Purpose.JUDGE: JudgeResult,
    Purpose.PARSE_SPEC: SpecResult,
    Purpose.POPULAR_QUESTIONS: PopularQuestionsResult,
}
