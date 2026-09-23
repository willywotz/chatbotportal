import uuid
from datetime import timedelta

import pytest

from app.core.errors import ApiError, ErrorCode
from app.features.agency.models.agency import Agency
from app.features.agency.models.evaluation import EvalResult
from app.core.utils import now

pytestmark = pytest.mark.asyncio


async def _agency(session, name="A"):
    ag = Agency(name=name, short_name=name, connection_type="API")
    session.add(ag)
    await session.flush()
    return ag


async def test_create_golden_question(db_session):
    from app.features.agency.services.agency_golden import create_golden_question

    agency = await _agency(db_session)
    gq = await create_golden_question(db_session, agency, "what is x?", ["topic"])
    assert gq.agency_id == agency.id
    assert gq.question == "what is x?"
    assert gq.expected_topics == ["topic"]


async def test_list_golden_questions_scoped_to_agency(db_session):
    from app.features.agency.services.agency_golden import create_golden_question, list_golden_questions

    agency_a = await _agency(db_session, "A")
    agency_b = await _agency(db_session, "B")
    await create_golden_question(db_session, agency_a, "q1", [])
    await create_golden_question(db_session, agency_b, "q2", [])

    questions = await list_golden_questions(db_session, agency_a)
    assert [q.question for q in questions] == ["q1"]


async def test_delete_golden_question_raises_404_when_missing(db_session):
    from app.features.agency.services.agency_golden import delete_golden_question

    agency = await _agency(db_session)
    with pytest.raises(ApiError) as exc:
        await delete_golden_question(db_session, agency, uuid.uuid4())
    assert exc.value.status == 404
    assert exc.value.code == ErrorCode.NOT_FOUND
    assert exc.value.message == "Golden question not found"


async def test_delete_golden_question_removes_the_row(db_session):
    from app.features.agency.repositories import evaluation as evaluation_repo
    from app.features.agency.services.agency_golden import create_golden_question, delete_golden_question

    agency = await _agency(db_session)
    gq = await create_golden_question(db_session, agency, "q1", [])
    await delete_golden_question(db_session, agency, gq.id)
    assert await evaluation_repo.get_golden(db_session, gq.id, agency.id) is None


async def test_list_eval_results_scoped_and_ordered(db_session):
    from app.features.agency.services.agency_golden import create_golden_question, list_eval_results

    agency = await _agency(db_session)
    gq = await create_golden_question(db_session, agency, "q1", [])
    # Explicit created_at: Postgres now() is stable within a transaction, so two
    # inserts in the same transaction would otherwise tie on the ORDER BY column.
    db_session.add_all([
        EvalResult(golden_question_id=gq.id, score=0.5, answer="a1", judge_reason="r1",
                   created_at=now() - timedelta(minutes=1)),
        EvalResult(golden_question_id=gq.id, score=0.9, answer="a2", judge_reason="r2", created_at=now()),
    ])
    await db_session.flush()

    results = await list_eval_results(db_session, agency, limit=1)
    assert len(results) == 1
    assert results[0].answer == "a2"
