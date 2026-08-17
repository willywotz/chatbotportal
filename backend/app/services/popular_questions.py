"""Popular Questions (คำถามยอดนิยม): curated + auto-generated FAQ list.

Auto-generation churn policy: rows created by ``regenerate`` are tagged
``source="auto"``; editing one (see ``app/routers/popular_questions.py``) flips
it to ``source="manual"`` so it survives future churn. A hidden row acts as a
tombstone — its ``text_key`` blocks the same question from being regenerated.
"""
import json
import logging
import re
import uuid
from datetime import timedelta

from fastapi import HTTPException, status
from tortoise.exceptions import DoesNotExist, IntegrityError

from app.config import settings
from app.models.agency import Agency
from app.models.conversation import Message
from app.models.popular_question import PopularQuestion, PopularQuestionSource
from app.schemas.popular_question import (
    PopularQuestionAgency,
    PopularQuestionCreate,
    PopularQuestionResponse,
    PopularQuestionUpdate,
)
from app.utils import clean_agency_ids, now

logger = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")
_TRAILING_PUNCT_RE = re.compile(r"[\s.,!?;:？！。，、]+$")
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)

_LLM_MAX_QUESTIONS = 8
_LLM_QUESTION_SAMPLE = 200

# 2 natural citizen questions per seeded agency (must match seeded agency names
# in app/routers/seed.py's DEFAULT_AGENCIES).
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


async def published_questions() -> list[dict]:
    """Rows to show publicly: not hidden, pinned first, capped at the display count."""
    rows = await PopularQuestion.filter(hidden=False).prefetch_related("agency")
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


async def regenerate() -> int:
    """Regenerate ``source="auto"`` rows from recent successful chat turns.

    Cold-start guarantee: below ``POPULAR_QUESTIONS_MIN_TURNS`` recent
    successful turns, this is a no-op so the seed rows stay visible.
    """
    cutoff = now() - timedelta(days=settings.POPULAR_QUESTIONS_WINDOW_DAYS)
    turn_count = await Message.filter(
        role="user", created_at__gte=cutoff, conversation__status="success",
    ).count()
    if turn_count < settings.POPULAR_QUESTIONS_MIN_TURNS:
        logger.info(
            "popular questions: only %d successful turns in the last %d days, skipping regen",
            turn_count, settings.POPULAR_QUESTIONS_WINDOW_DAYS,
        )
        return 0

    user_rows = await Message.filter(
        role="user", created_at__gte=cutoff, conversation__status="success",
    ).order_by("-created_at").limit(_LLM_QUESTION_SAMPLE).values("id", "content")

    samples = await _build_samples(list(user_rows))
    candidates = await _ask_llm(samples)
    if not candidates:
        return 0

    # Churn: drop stale auto-generated rows that were never pinned or hidden.
    await PopularQuestion.filter(source=PopularQuestionSource.auto, pinned=False, hidden=False).delete()

    # Only agencies we actually fed the LLM are valid targets — blocks hallucinated ids.
    valid_ids = {a["id"] for s in samples for a in s["agencies"]}
    agency_by_id: dict[str, Agency] = {}
    if valid_ids:
        for ag in await Agency.filter(id__in=valid_ids):
            agency_by_id[str(ag.id)] = ag

    created = 0
    for cand in candidates[:_LLM_MAX_QUESTIONS]:
        text = str(cand.get("text") or "").strip()
        if not text:
            continue
        key = normalize_text_key(text)
        if await PopularQuestion.filter(text_key=key).exists():
            continue  # any existing row (incl. a hidden tombstone) blocks recreation

        agency = agency_by_id.get(str(cand.get("agency_id") or "").strip())

        score = cand.get("score")
        try:
            score = float(score) if score is not None else None
        except (TypeError, ValueError):
            score = None

        await PopularQuestion.create(
            text=text, text_key=key, agency=agency, source=PopularQuestionSource.auto, score=score,
        )
        created += 1
    return created


def _extract_json_payload(text: str) -> str:
    """Strip a Markdown code fence, or any leading/trailing prose, around a JSON payload.

    Real chat models often wrap JSON in ```json fences or add a sentence
    before/after it; this recovers the payload so ``json.loads`` still works.
    """
    fenced = _FENCE_RE.search(text)
    if fenced:
        return fenced.group(1).strip()
    start = next((i for i, ch in enumerate(text) if ch in "{["), None)
    if start is None:
        return text.strip()
    end = max(text.rfind("}"), text.rfind("]"))
    if end < start:
        return text.strip()
    return text[start:end + 1]


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


async def _build_samples(user_rows: list[dict]) -> list[dict]:
    """Pair each question with the agencies its assistant reply resolved to."""
    user_ids = [r["id"] for r in user_rows]
    agency_ids_by_parent: dict = {}
    all_ids: set[str] = set()
    if user_ids:
        replies = await Message.filter(
            role="assistant", parent_id__in=user_ids,
        ).values("parent_id", "agency_ids")
        for reply in replies:
            ids = clean_agency_ids(reply["agency_ids"])
            agency_ids_by_parent[reply["parent_id"]] = ids
            all_ids.update(ids)
    name_by_id: dict[str, str] = {}
    if all_ids:
        for ag in await Agency.filter(id__in=list(all_ids)).values("id", "name"):
            name_by_id[str(ag["id"])] = ag["name"]
    samples: list[dict] = []
    for r in user_rows:
        agencies = [
            {"id": aid, "name": name_by_id[aid]}
            for aid in agency_ids_by_parent.get(r["id"], [])
            if aid in name_by_id
        ]
        samples.append({"text": r["content"], "agencies": agencies})
    return samples


async def _ask_llm(samples: list[dict]) -> list[dict]:
    from app.services.llm import LlmError, Purpose, chat
    prompt = _LLM_PROMPT.format(
        k=_LLM_MAX_QUESTIONS,
        agencies=_format_agency_reference(samples),
        questions="\n".join(_format_question(s) for s in samples),
    )
    try:
        res = await chat(purpose=Purpose.POPULAR_QUESTIONS, messages=[{"role": "user", "content": prompt}])
        data = json.loads(_extract_json_payload(res.content))
        candidates = data.get("questions", [])
        return candidates if isinstance(candidates, list) else []
    except (LlmError, json.JSONDecodeError, ValueError, TypeError, AttributeError) as e:
        logger.error("popular questions LLM call failed: %s", e)
        return []


async def to_response(pq: PopularQuestion) -> PopularQuestionResponse:
    agency = await pq.agency if pq.agency_id else None
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


async def list_questions() -> list[PopularQuestion]:
    return await PopularQuestion.all().prefetch_related("agency")


async def get_question_or_404(question_id: uuid.UUID) -> PopularQuestion:
    try:
        return await PopularQuestion.get(id=question_id)
    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Popular question not found")


async def create_question(body: PopularQuestionCreate) -> PopularQuestion:
    if body.agency_id is not None and not await Agency.filter(id=body.agency_id).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agency not found")

    text = body.text.strip()
    try:
        return await PopularQuestion.create(
            text=text,
            text_key=normalize_text_key(text),
            agency_id=body.agency_id,
            source=PopularQuestionSource.manual,
            pinned=body.pinned,
            hidden=body.hidden,
            sort_order=body.sort_order,
        )
    except IntegrityError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="a question with this text already exists")


async def update_question(question_id: uuid.UUID, body: PopularQuestionUpdate) -> PopularQuestion:
    pq = await get_question_or_404(question_id)

    if body.agency_id is not None and not await Agency.filter(id=body.agency_id).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agency not found")

    update_data = body.model_dump(exclude_unset=True)
    if update_data.get("text") is not None:
        new_text = update_data["text"].strip()
        update_data["text"] = new_text
        if new_text != pq.text:
            update_data["text_key"] = normalize_text_key(new_text)
            if pq.source == PopularQuestionSource.auto:
                update_data["source"] = PopularQuestionSource.manual

    try:
        await pq.update_from_dict(update_data).save()
    except IntegrityError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="a question with this text already exists")
    return pq


async def delete_question(question_id: uuid.UUID) -> None:
    pq = await get_question_or_404(question_id)
    await pq.delete()


async def seed_popular_questions() -> int:
    """Idempotent seed of natural citizen questions, 2 per seeded agency."""
    created = 0
    for agency_name, text in _SEED_QUESTIONS:
        agency = await Agency.filter(name=agency_name).first()
        _, was_created = await PopularQuestion.get_or_create(
            text_key=normalize_text_key(text),
            defaults={"text": text, "agency": agency, "source": PopularQuestionSource.seed},
        )
        created += int(was_created)
    return created
