"""Popular Questions (คำถามยอดนิยม): curated + auto-generated FAQ list.

Auto-generation churn policy: rows created by ``regenerate`` are tagged
``source="auto"``; editing one (see ``app/routers/popular_questions.py``) flips
it to ``source="manual"`` so it survives future churn. A hidden row acts as a
tombstone — its ``text_key`` blocks the same question from being regenerated.
"""
import logging
import re
import uuid
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ApiError, ErrorCode
from app.features.analytics.models.popular_question import PopularQuestion, PopularQuestionSource
from app.features.agency.repositories import agency as agency_repo
from app.features.analytics.repositories import popular_question as popular_question_repo
from app.features.analytics.schemas.popular_question import (
    PopularQuestionAgency,
    PopularQuestionCreate,
    PopularQuestionResponse,
    PopularQuestionUpdate,
)
from app.core.utils import clean_agency_ids, now

logger = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")
_TRAILING_PUNCT_RE = re.compile(r"[\s.,!?;:？！。，、]+$")

_LLM_MAX_QUESTIONS = 8
_LLM_QUESTION_SAMPLE = 200

# 2 natural citizen questions per seeded agency (must match seeded agency names
# in app/services/seed.py's DEFAULT_AGENCIES).
_SEED_QUESTIONS = [
    ("กรมการปกครอง", "ทำบัตรประชาชนใหม่ ต้องใช้เอกสารอะไรบ้าง"),
    ("กรมการปกครอง", "ย้ายทะเบียนบ้านออนไลน์ทำอย่างไร"),
    ("กรมที่ดิน", "ตรวจสอบราคาประเมินที่ดินทำอย่างไร"),
    ("กรมที่ดิน", "ขอคัดสำเนาโฉนดที่ดินต้องทำอย่างไร"),
    ("สำนักงานคณะกรรมการอาหารและยา", "ตรวจสอบเลขทะเบียน อย. ของผลิตภัณฑ์ได้ที่ไหน"),
    ("สำนักงานคณะกรรมการอาหารและยา", "ยาพาราเซตามอลต้องขึ้นทะเบียน อย. หรือไม่"),
]

_LLM_PROMPT = """\
คุณเป็นผู้ช่วยวิเคราะห์คำถามยอดนิยมของประชาชนที่ถามเข้าระบบพอร์ทัลบริการภาครัฐ
จากรายการคำถามของผู้ใช้ด้านล่าง (แต่ละข้อมีหน่วยงานที่เกี่ยวข้องกำกับไว้ในวงเล็บ)
ให้เลือกและเรียบเรียงคำถามที่พบบ่อยที่สุดไม่เกิน {k} ข้อ เป็นคำถามภาษาไทยที่กระชับและชัดเจน
สำหรับแต่ละข้อ ให้ระบุ agency_id โดยเลือกจาก "หน่วยงานอ้างอิง" ด้านล่างที่ตรงที่สุด (ถ้าไม่มีที่ตรงให้เว้นว่าง)

หน่วยงานอ้างอิง:
{agencies}

รายการคำถาม:
{questions}

ตอบเป็น JSON เท่านั้น ไม่มีข้อความอื่นปน ในรูปแบบ:
{{"questions": [{{"text": "<คำถาม>", "agency_id": "<id หน่วยงาน หรือค่าว่าง>", "score": <ตัวเลข 0.0-1.0>}}]}}
"""


def normalize_text_key(text: str) -> str:
    """Dedupe key: trim, collapse internal whitespace, strip trailing punctuation, casefold."""
    collapsed = _WHITESPACE_RE.sub(" ", text.strip())
    stripped = _TRAILING_PUNCT_RE.sub("", collapsed)
    return stripped.casefold()


async def published_questions(session: AsyncSession) -> list[dict]:
    """Rows to show publicly: not hidden, pinned first, capped at the display count."""
    rows = await popular_question_repo.visible_with_agency(session)
    rows.sort(key=lambda r: (
        0 if r.pinned else 1,
        r.sort_order,
        0 if r.score is not None else 1,
        -(r.score or 0.0),
        -r.created_at.timestamp(),
    ))
    out: list[dict] = []
    for r in rows[: settings.POPULAR_QUESTIONS_DISPLAY_COUNT]:
        agency = r.agency if r.agency_id else None
        out.append({
            "id": str(r.id),
            "text": r.text,
            "agency": {"id": str(agency.id), "name": agency.name, "logo": agency.logo} if agency else None,
        })
    return out


async def regenerate(session: AsyncSession) -> int:
    """Regenerate ``source="auto"`` rows from recent successful chat turns.

    Cold-start guarantee: below ``POPULAR_QUESTIONS_MIN_TURNS`` recent
    successful turns, this is a no-op so the seed rows stay visible.
    """
    cutoff = now() - timedelta(days=settings.POPULAR_QUESTIONS_WINDOW_DAYS)
    turn_count = await popular_question_repo.recent_successful_turn_count(session, cutoff)
    if turn_count < settings.POPULAR_QUESTIONS_MIN_TURNS:
        logger.info(
            "popular questions: only %d successful turns in the last %d days, skipping regen",
            turn_count, settings.POPULAR_QUESTIONS_WINDOW_DAYS,
        )
        return 0

    user_rows = await popular_question_repo.recent_successful_user_messages(
        session, cutoff, _LLM_QUESTION_SAMPLE)

    samples = await _build_samples(session, user_rows)
    candidates = await _ask_llm(session, samples)
    if not candidates:
        return 0

    # Churn: drop stale auto-generated rows that were never pinned or hidden.
    await popular_question_repo.delete_stale_auto(session)

    # Only agencies we actually fed the LLM are valid targets — blocks hallucinated ids.
    valid_ids = {a["id"] for s in samples for a in s["agencies"]}
    agency_by_id: dict = {}
    if valid_ids:
        for ag in await agency_repo.by_ids(session, list(valid_ids)):
            agency_by_id[str(ag.id)] = ag

    created = 0
    for cand in candidates[:_LLM_MAX_QUESTIONS]:
        text = str(cand.get("text") or "").strip()
        if not text:
            continue
        key = normalize_text_key(text)
        if await popular_question_repo.text_key_exists(session, key):
            continue  # any existing row (incl. a hidden tombstone) blocks recreation

        agency = agency_by_id.get(str(cand.get("agency_id") or "").strip())

        score = cand.get("score")
        try:
            score = float(score) if score is not None else None
        except (TypeError, ValueError):
            score = None

        await popular_question_repo.create(
            session, text=text, text_key=key, agency=agency, source=PopularQuestionSource.auto, score=score,
        )
        created += 1
    return created


def _format_agency_reference(samples: list[dict]) -> str:
    seen: dict[str, str] = {}
    for sample in samples:
        for agency in sample["agencies"]:
            seen[agency["id"]] = agency["name"]
    if not seen:
        return "(ไม่มี)"
    return "\n".join(f"{name} = {aid}" for aid, name in seen.items())


def _format_question(sample: dict) -> str:
    names = ", ".join(a["name"] for a in sample["agencies"]) or "ไม่ทราบ"
    return f"- {sample['text']}  [หน่วยงาน: {names}]"


async def _build_samples(session: AsyncSession, user_rows: list[dict]) -> list[dict]:
    """Pair each question with the agencies its assistant reply resolved to."""
    user_ids = [r["id"] for r in user_rows]
    agency_ids_by_parent: dict = {}
    all_ids: set[str] = set()
    if user_ids:
        replies = await popular_question_repo.assistant_replies_for(session, user_ids)
        for reply in replies:
            ids = clean_agency_ids(reply["agency_ids"])
            agency_ids_by_parent[reply["parent_id"]] = ids
            all_ids.update(ids)
    name_by_id: dict[str, str] = {}
    if all_ids:
        for ag in await agency_repo.by_ids(session, list(all_ids)):
            name_by_id[str(ag.id)] = ag.name
    samples: list[dict] = []
    for r in user_rows:
        agencies = [
            {"id": aid, "name": name_by_id[aid]}
            for aid in agency_ids_by_parent.get(r["id"], [])
            if aid in name_by_id
        ]
        samples.append({"text": r["content"], "agencies": agencies})
    return samples


async def _ask_llm(session: AsyncSession, samples: list[dict]) -> list[dict]:
    from app.features.llm.services import LlmError, Purpose, parse
    prompt = _LLM_PROMPT.format(
        k=_LLM_MAX_QUESTIONS,
        agencies=_format_agency_reference(samples),
        questions="\n".join(_format_question(s) for s in samples),
    )
    try:
        result = await parse(session, Purpose.POPULAR_QUESTIONS,
                             messages=[{"role": "user", "content": prompt}])
        return [q.model_dump() for q in result.questions]
    except (LlmError, Exception) as e:
        logger.error("popular questions LLM call failed: %s", e)
        return []


async def to_response(session: AsyncSession, pq: PopularQuestion) -> PopularQuestionResponse:
    agency = await agency_repo.by_id(session, pq.agency_id) if pq.agency_id else None
    return PopularQuestionResponse(
        id=pq.id,
        text=pq.text,
        agency=PopularQuestionAgency(id=agency.id, name=agency.name, logo=agency.logo) if agency else None,
        source=pq.source,
        pinned=pq.pinned,
        hidden=pq.hidden,
        sort_order=pq.sort_order,
        score=pq.score,
        created_at=pq.created_at,
        updated_at=pq.updated_at,
    )


async def list_questions(session: AsyncSession) -> list[PopularQuestion]:
    return await popular_question_repo.all_with_agency(session)


async def get_question_or_404(session: AsyncSession, question_id: uuid.UUID) -> PopularQuestion:
    pq = await popular_question_repo.by_id(session, question_id)
    if pq is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Popular question not found", status=404)
    return pq


async def create_question(session: AsyncSession, body: PopularQuestionCreate) -> PopularQuestion:
    if body.agency_id is not None and await agency_repo.by_id(session, body.agency_id) is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Agency not found", status=404)

    text = body.text.strip()
    key = normalize_text_key(text)
    if await popular_question_repo.text_key_exists(session, key):
        raise ApiError(ErrorCode.CONFLICT, "a question with this text already exists", status=409)
    return await popular_question_repo.create(
        session,
        text=text,
        text_key=key,
        agency_id=body.agency_id,
        source=PopularQuestionSource.manual,
        pinned=body.pinned,
        hidden=body.hidden,
        sort_order=body.sort_order,
    )


async def update_question(session: AsyncSession, question_id: uuid.UUID, body: PopularQuestionUpdate) -> PopularQuestion:
    pq = await get_question_or_404(session, question_id)

    if body.agency_id is not None and await agency_repo.by_id(session, body.agency_id) is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Agency not found", status=404)

    update_data = body.model_dump(exclude_unset=True)
    if update_data.get("text") is not None:
        new_text = update_data["text"].strip()
        update_data["text"] = new_text
        if new_text != pq.text:
            new_key = normalize_text_key(new_text)
            if await popular_question_repo.text_key_exists(session, new_key, exclude_id=pq.id):
                raise ApiError(ErrorCode.CONFLICT, "a question with this text already exists", status=409)
            update_data["text_key"] = new_key
            if pq.source == PopularQuestionSource.auto:
                update_data["source"] = PopularQuestionSource.manual

    return await popular_question_repo.update(session, pq, update_data)


async def delete_question(session: AsyncSession, question_id: uuid.UUID) -> None:
    pq = await get_question_or_404(session, question_id)
    await popular_question_repo.delete(session, pq)


async def seed_popular_questions(session: AsyncSession) -> int:
    """Idempotent seed of natural citizen questions, 2 per seeded agency."""
    created = 0
    for agency_name, text in _SEED_QUESTIONS:
        key = normalize_text_key(text)
        if await popular_question_repo.text_key_exists(session, key):
            continue
        agency = await agency_repo.by_name(session, agency_name)
        await popular_question_repo.create(
            session, text=text, text_key=key, agency=agency, source=PopularQuestionSource.seed,
        )
        created += 1
    return created
