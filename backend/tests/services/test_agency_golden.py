import pytest

from app.errors import ApiError, ErrorCode


@pytest.mark.asyncio
async def test_create_golden_question(db):
    from app.models import Agency
    from app.services.agency_golden import create_golden_question

    agency = await Agency.create(name="A", short_name="A", connection_type="API")
    gq = await create_golden_question(agency, "what is x?", ["topic"])
    assert gq.agency_id == agency.id
    assert gq.question == "what is x?"
    assert gq.expected_topics == ["topic"]


@pytest.mark.asyncio
async def test_list_golden_questions_scoped_to_agency(db):
    from app.models import Agency
    from app.services.agency_golden import create_golden_question, list_golden_questions

    agency_a = await Agency.create(name="A", short_name="A", connection_type="API")
    agency_b = await Agency.create(name="B", short_name="B", connection_type="API")
    await create_golden_question(agency_a, "q1", [])
    await create_golden_question(agency_b, "q2", [])

    questions = await list_golden_questions(agency_a)
    assert [q.question for q in questions] == ["q1"]


@pytest.mark.asyncio
async def test_delete_golden_question_raises_404_when_missing(db):
    import uuid

    from app.models import Agency
    from app.services.agency_golden import delete_golden_question

    agency = await Agency.create(name="A", short_name="A", connection_type="API")
    with pytest.raises(ApiError) as exc:
        await delete_golden_question(agency, uuid.uuid4())
    assert exc.value.status == 404
    assert exc.value.code == ErrorCode.NOT_FOUND
    assert exc.value.message == "Golden question not found"


@pytest.mark.asyncio
async def test_delete_golden_question_removes_the_row(db):
    from app.models.evaluation import GoldenQuestion
    from app.models import Agency
    from app.services.agency_golden import create_golden_question, delete_golden_question

    agency = await Agency.create(name="A", short_name="A", connection_type="API")
    gq = await create_golden_question(agency, "q1", [])
    await delete_golden_question(agency, gq.id)
    assert await GoldenQuestion.get_or_none(id=gq.id) is None


@pytest.mark.asyncio
async def test_list_eval_results_scoped_and_ordered(db):
    from app.models import Agency, EvalResult
    from app.services.agency_golden import create_golden_question, list_eval_results

    agency = await Agency.create(name="A", short_name="A", connection_type="API")
    gq = await create_golden_question(agency, "q1", [])
    await EvalResult.create(golden_question=gq, score=0.5, answer="a1", judge_reason="r1")
    await EvalResult.create(golden_question=gq, score=0.9, answer="a2", judge_reason="r2")

    results = await list_eval_results(agency, limit=1)
    assert len(results) == 1
    assert results[0].answer == "a2"
