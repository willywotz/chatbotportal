"""Scheduled answer-quality evaluation: dispatch golden questions, LLM-judge the answers."""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal
from app.core.utils import now
from app.features.agency.models.agency import Agency
from app.features.agency.repositories import evaluation as evaluation_repo
from app.features.chat.services.dispatch import dispatch_one

logger = logging.getLogger(__name__)


async def _ask(agency: Agency, question: str) -> dict:
    route = {
        "agency_id": str(agency.id), "agency_name": agency.name,
        "connection_type": agency.connection_type, "endpoint_url": agency.endpoint_url,
        "sub_question": question, "expected_payload": agency.expected_payload,
        "api_headers": agency.api_headers, "dispatch_timeout_s": agency.dispatch_timeout_s,
    }
    start = now()
    result = await dispatch_one(route, conversation_id="")
    latency_ms = int((now() - start).total_seconds() * 1000)
    ok = result.get("status") == "ok"
    return {"ok": ok, "latency_ms": latency_ms,
            "answer": str(result.get("response", "")), "error": None if ok else result.get("response")}

_JUDGE_PROMPT = """\
คุณเป็นผู้ตรวจคุณภาพคำตอบบริการภาครัฐ ให้คะแนนคำตอบ 0.0–1.0
คำถาม: {question}
หัวข้อที่คำตอบควรครอบคลุม: {topics}
คำตอบที่ได้: {answer}

ตอบเป็น JSON เท่านั้น: {{"score": <float>, "reason": "<สั้นๆ>"}}"""


async def run_evaluation() -> int:
    ran = 0
    async with AsyncSessionLocal() as session, session.begin():
        questions = await evaluation_repo.all_golden_with_agency(session)
    for gq in questions:
        if gq.agency.status != "active":
            continue
        try:
            res = await _ask(gq.agency, gq.question)
            answer = res["answer"] if res["ok"] else ""
            async with AsyncSessionLocal() as session, session.begin():
                score, reason = await _judge(session, gq.question, gq.expected_topics, answer)
                await evaluation_repo.create_eval_result(
                    session, golden_question_id=gq.id, score=score, answer=answer, judge_reason=reason,
                )
            ran += 1
        except Exception:
            logger.exception("eval failed for question %s", gq.id)
    return ran


async def _judge(session: AsyncSession, question: str, topics: list, answer: str) -> tuple[float, str]:
    if not answer.strip():
        return 0.0, "no answer from agency"
    prompt = _JUDGE_PROMPT.format(question=question, topics=", ".join(topics), answer=answer[:4000])
    from app.features.llm.services import Purpose, parse
    result = await parse(session, Purpose.JUDGE, messages=[{"role": "user", "content": prompt}])
    return float(result.score), str(result.reason)
