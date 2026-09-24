from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.features.agency.models.agency import Agency
from app.features.agency.models.evaluation import EvalResult, GoldenQuestion
from app.features.agency.repositories import evaluation as evaluation_repo
from app.features.agency.services import evaluation
from app.features.llm.services.result_schemas import JudgeResult

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _bind_evaluation_session(db_session, monkeypatch):
    """run_evaluation opens its own session; bind it to the test's connection
    (same DB transaction) so writes are visible/rolled back with the test."""
    conn = await db_session.connection()
    factory = async_sessionmaker(
        bind=conn, class_=AsyncSession, expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(evaluation, "AsyncSessionLocal", factory)


async def test_eval_run_scores_each_question(db_session, monkeypatch):
    ag = Agency(name="A", status="active", connection_type="API", endpoint_url="http://x")
    db_session.add(ag)
    await db_session.flush()
    gq = GoldenQuestion(agency_id=ag.id, question="ทำบัตรประชาชนที่ไหน",
                         expected_topics=["สถานที่", "เอกสาร"])
    db_session.add(gq)
    await db_session.flush()

    async def fake_ask(agency, question):
        return {"ok": True, "latency_ms": 10, "answer": "ไปที่สำนักงานเขต ใช้บัตรเดิม"}

    async def fake_judge(session, *a, **kw):
        return JudgeResult(score=0.8, reason="covers both")

    monkeypatch.setattr(evaluation, "_ask", fake_ask)
    monkeypatch.setattr("app.features.llm.services.parse", fake_judge)

    ran = await evaluation.run_evaluation()

    assert ran == 1
    results = await evaluation_repo.list_eval_results(db_session, [gq.id], limit=10)
    assert results[0].score == 0.8 and "สำนักงานเขต" in results[0].answer


async def test_eval_judge_calls_chat_with_session(db_session, monkeypatch):
    """chat() is session-first; _judge must thread the enclosing session through."""
    ag = Agency(name="B", status="active", connection_type="API", endpoint_url="http://x")
    db_session.add(ag)
    await db_session.flush()
    gq = GoldenQuestion(agency_id=ag.id, question="test question", expected_topics=["a"])
    db_session.add(gq)
    await db_session.flush()

    async def fake_ask(agency, question):
        return {"ok": True, "latency_ms": 10, "answer": "some answer"}

    fake_parse = AsyncMock(return_value=JudgeResult(score=0.5, reason="ok"))

    monkeypatch.setattr(evaluation, "_ask", fake_ask)
    monkeypatch.setattr("app.features.llm.services.parse", fake_parse)

    ran = await evaluation.run_evaluation()

    assert ran == 1
    assert isinstance(fake_parse.call_args.args[0], AsyncSession)


async def test_eval_skips_inactive_agencies(db_session, monkeypatch):
    ag = Agency(name="Inactive", status="draft", connection_type="API", endpoint_url="http://x")
    db_session.add(ag)
    await db_session.flush()
    db_session.add(GoldenQuestion(agency_id=ag.id, question="test question", expected_topics=[]))
    await db_session.flush()

    called = []

    async def fake_ask(agency, question):
        called.append(question)
        return {"ok": True, "latency_ms": 10, "answer": "answer"}

    monkeypatch.setattr(evaluation, "_ask", fake_ask)

    ran = await evaluation.run_evaluation()
    assert ran == 0
    assert called == []
