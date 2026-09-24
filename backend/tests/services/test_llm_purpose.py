from app.features.llm.services.purpose import Purpose, KNOWN_PURPOSES, PURPOSE_SCHEMAS
from app.features.llm.services.result_schemas import (
    ClassificationResult, JudgeResult, SpecResult, PopularQuestionsResult,
)


def test_known_purposes():
    assert KNOWN_PURPOSES == (
        "classification", "brief", "judge", "parse_spec", "popular_questions")


def test_schema_map():
    assert PURPOSE_SCHEMAS[Purpose.CLASSIFICATION] is ClassificationResult
    assert PURPOSE_SCHEMAS[Purpose.BRIEF] is None
    assert PURPOSE_SCHEMAS[Purpose.JUDGE] is JudgeResult


def test_judge_result_validates():
    r = JudgeResult(score=0.8, reason="ok")
    assert r.score == 0.8


def test_spec_result_nested():
    r = SpecResult(auth_method="api_key", auth_header="X-API-Key", base_path="/v1",
                   request_format="json",
                   endpoints=[{"method": "GET", "path": "/x", "description": "d"}],
                   response_schema=[{"field": "a", "type": "string", "description": "d"}])
    assert r.endpoints[0].method == "GET"


def test_popular_questions_result():
    r = PopularQuestionsResult(questions=[{"text": "q", "agency_id": None}])
    assert r.questions[0].text == "q"
