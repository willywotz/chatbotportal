def test_public_surface():
    from app.features.llm.services import (
        chat, parse, ping, Purpose, KNOWN_PURPOSES, LlmError, invalidate,
        ClassificationResult, JudgeResult, SpecResult, PopularQuestionsResult,
    )
    assert callable(chat) and callable(parse)
