"""Tests for app.services.popular_questions."""
import uuid

import pytest
from fastapi import HTTPException

from app.models import Agency, Conversation, Message
from app.models.popular_question import PopularQuestion, PopularQuestionSource
from app.schemas.popular_question import PopularQuestionCreate, PopularQuestionUpdate
from app.services import popular_questions as pq_service
from app.services.llm import LlmResult, LlmUsageInfo


def _fake_llm_result(content: str) -> LlmResult:
    return LlmResult(
        content=content, tool_calls=None,
        usage=LlmUsageInfo(model="m", prompt_tokens=0, completion_tokens=0, cost_usd=None),
        raw={},
    )


class TestNormalizeTextKey:
    def test_collapses_internal_whitespace(self):
        assert pq_service.normalize_text_key("ทำบัตร   ประชาชน  ใหม่") == "ทำบัตร ประชาชน ใหม่"

    def test_trims_leading_and_trailing_whitespace(self):
        assert pq_service.normalize_text_key("   ย้ายทะเบียนบ้าน   ") == "ย้ายทะเบียนบ้าน"

    def test_strips_trailing_punctuation(self):
        assert pq_service.normalize_text_key("ทำบัตรประชาชนอย่างไร???") == "ทำบัตรประชาชนอย่างไร"

    def test_casefolds(self):
        assert pq_service.normalize_text_key("How To Renew ID?") == "how to renew id"

    def test_same_question_different_formatting_yields_same_key(self):
        a = pq_service.normalize_text_key("  ทำบัตรประชาชนใหม่  ต้องใช้อะไรบ้าง？")
        b = pq_service.normalize_text_key("ทำบัตรประชาชนใหม่ ต้องใช้อะไรบ้าง")
        assert a == b


@pytest.mark.asyncio
async def test_published_excludes_hidden(db):
    await PopularQuestion.create(text="visible", text_key="visible", source="seed", hidden=False)
    await PopularQuestion.create(text="secret", text_key="secret", source="seed", hidden=True)

    rows = await pq_service.published_questions()

    assert [r["text"] for r in rows] == ["visible"]


@pytest.mark.asyncio
async def test_published_pinned_first(db):
    await PopularQuestion.create(text="unpinned", text_key="unpinned", source="seed", pinned=False)
    await PopularQuestion.create(text="pinned", text_key="pinned", source="seed", pinned=True)

    rows = await pq_service.published_questions()

    assert rows[0]["text"] == "pinned"


@pytest.mark.asyncio
async def test_published_orders_by_sort_order_within_pinned(db):
    await PopularQuestion.create(text="second", text_key="second", source="seed", pinned=True, sort_order=2)
    await PopularQuestion.create(text="first", text_key="first", source="seed", pinned=True, sort_order=1)

    rows = await pq_service.published_questions()

    assert [r["text"] for r in rows] == ["first", "second"]


@pytest.mark.asyncio
async def test_published_orders_by_score_desc_nulls_last(db):
    await PopularQuestion.create(text="no_score", text_key="no_score", source="seed", score=None)
    await PopularQuestion.create(text="high", text_key="high", source="seed", score=0.9)
    await PopularQuestion.create(text="low", text_key="low", source="seed", score=0.1)

    rows = await pq_service.published_questions()

    assert [r["text"] for r in rows] == ["high", "low", "no_score"]


@pytest.mark.asyncio
async def test_published_falls_back_to_recency(db):
    older = await PopularQuestion.create(text="older", text_key="older", source="seed")
    newer = await PopularQuestion.create(text="newer", text_key="newer", source="seed")
    older.created_at = newer.created_at.replace(year=newer.created_at.year - 1)
    await older.save(update_fields=["created_at"])

    rows = await pq_service.published_questions()

    assert [r["text"] for r in rows] == ["newer", "older"]


@pytest.mark.asyncio
async def test_published_caps_at_display_count(db, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_DISPLAY_COUNT", 2)
    for i in range(5):
        await PopularQuestion.create(text=f"q{i}", text_key=f"q{i}", source="seed")

    rows = await pq_service.published_questions()

    assert len(rows) == 2


@pytest.mark.asyncio
async def test_published_resolves_agency(db):
    ag = await Agency.create(name="กรมการปกครอง", logo="🏛️")
    await PopularQuestion.create(text="with agency", text_key="with_agency", source="seed", agency=ag)
    await PopularQuestion.create(text="no agency", text_key="no_agency", source="seed")

    rows = await pq_service.published_questions()
    by_text = {r["text"]: r for r in rows}

    assert by_text["with agency"]["agency"] == {"id": str(ag.id), "name": "กรมการปกครอง", "logo": "🏛️"}
    assert by_text["no agency"]["agency"] is None


@pytest.mark.asyncio
async def test_ask_llm_parses_markdown_fenced_json(monkeypatch):
    content = '```json\n{"questions": [{"text": "คำถาม1", "agency_id": "", "score": 0.5}]}\n```'

    async def fake_chat(**_kwargs):
        return _fake_llm_result(content)

    monkeypatch.setattr("app.services.llm.chat", fake_chat)

    result = await pq_service._ask_llm([{"text": "q", "agencies": []}])

    assert result == [{"text": "คำถาม1", "agency_id": "", "score": 0.5}]


@pytest.mark.asyncio
async def test_ask_llm_parses_json_with_leading_prose(monkeypatch):
    content = 'นี่คือคำถามยอดนิยม:\n{"questions": [{"text": "q2", "agency_id": "", "score": 0.3}]}\nขอบคุณครับ'

    async def fake_chat(**_kwargs):
        return _fake_llm_result(content)

    monkeypatch.setattr("app.services.llm.chat", fake_chat)

    result = await pq_service._ask_llm([{"text": "q", "agencies": []}])

    assert result == [{"text": "q2", "agency_id": "", "score": 0.3}]


@pytest.mark.asyncio
async def test_ask_llm_returns_empty_on_garbage_output(monkeypatch):
    async def fake_chat(**_kwargs):
        return _fake_llm_result("ขอโทษครับ ไม่สามารถตอบคำถามนี้ได้")

    monkeypatch.setattr("app.services.llm.chat", fake_chat)

    result = await pq_service._ask_llm([{"text": "q", "agencies": []}])

    assert result == []


async def _make_successful_turns(n: int, question: str = "คำถามทดสอบ", agency_ids=None) -> None:
    for _ in range(n):
        conv = await Conversation.create(status="success")
        user_msg = await Message.create(conversation=conv, role="user", content=question)
        await Message.create(
            conversation=conv, role="assistant", parent_id=user_msg.id,
            content="ตอบ", agency_ids=agency_ids or [],
        )


@pytest.mark.asyncio
async def test_regenerate_noop_below_min_turns(db, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 20)
    await _make_successful_turns(5)
    seed = await PopularQuestion.create(text="seed q", text_key="seed_q", source="seed")

    called = False

    async def fake_ask_llm(_questions):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)

    created = await pq_service.regenerate()

    assert created == 0
    assert called is False
    assert await PopularQuestion.filter(id=seed.id).exists()


@pytest.mark.asyncio
async def test_regenerate_deletes_unpinned_unhidden_auto_rows_and_inserts_fresh(db, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    await _make_successful_turns(3)
    stale = await PopularQuestion.create(text="stale auto", text_key="stale_auto", source="auto")

    async def fake_ask_llm(_questions):
        return [{"text": "new auto question", "agency": "", "score": 0.7}]

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)

    created = await pq_service.regenerate()

    assert created == 1
    assert not await PopularQuestion.filter(id=stale.id).exists()
    fresh = await PopularQuestion.get(text_key=pq_service.normalize_text_key("new auto question"))
    assert fresh.source == PopularQuestionSource.auto


@pytest.mark.asyncio
async def test_regenerate_preserves_pinned_auto_row(db, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    await _make_successful_turns(3)
    pinned = await PopularQuestion.create(text="pinned auto", text_key="pinned_auto", source="auto", pinned=True)

    async def fake_ask_llm(_questions):
        return []

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)

    await pq_service.regenerate()

    assert await PopularQuestion.filter(id=pinned.id).exists()


@pytest.mark.asyncio
async def test_regenerate_never_touches_manual_or_seed_rows(db, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    await _make_successful_turns(3)
    manual = await PopularQuestion.create(text="manual q", text_key="manual_q", source="manual")
    seed = await PopularQuestion.create(text="seed q", text_key="seed_q", source="seed")

    async def fake_ask_llm(_questions):
        return []

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)

    await pq_service.regenerate()

    assert await PopularQuestion.filter(id=manual.id).exists()
    assert await PopularQuestion.filter(id=seed.id).exists()


@pytest.mark.asyncio
async def test_regenerate_skips_candidate_matching_hidden_tombstone(db, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    await _make_successful_turns(3)
    key = pq_service.normalize_text_key("ห้ามกลับมาอีก")
    await PopularQuestion.create(text="ห้ามกลับมาอีก", text_key=key, source="auto", hidden=True)

    async def fake_ask_llm(_questions):
        return [{"text": "ห้ามกลับมาอีก", "agency": "", "score": 0.5}]

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)

    created = await pq_service.regenerate()

    assert created == 0
    assert await PopularQuestion.filter(text_key=key).count() == 1


@pytest.mark.asyncio
async def test_regenerate_feeds_known_agency_to_llm_and_resolves(db, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    ag = await Agency.create(name="กรมที่ดิน")
    await _make_successful_turns(2, question="ขอคัดโฉนด", agency_ids=[str(ag.id)])

    captured = {}

    async def fake_chat(**kwargs):
        captured["prompt"] = kwargs["messages"][0]["content"]
        return _fake_llm_result(
            f'{{"questions": [{{"text": "ขอคัดโฉนดที่ดิน", "agency_id": "{ag.id}", "score": 0.8}}]}}'
        )

    monkeypatch.setattr("app.services.llm.chat", fake_chat)

    await pq_service.regenerate()

    assert "กรมที่ดิน" in captured["prompt"]
    assert str(ag.id) in captured["prompt"]
    row = await PopularQuestion.get(text_key=pq_service.normalize_text_key("ขอคัดโฉนดที่ดิน"))
    assert row.agency_id == ag.id


@pytest.mark.asyncio
async def test_regenerate_resolves_agency_by_id(db, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    ag = await Agency.create(name="กรมที่ดิน")
    await _make_successful_turns(3, agency_ids=[str(ag.id)])

    async def fake_ask_llm(_samples):
        return [{"text": "เกี่ยวกับที่ดิน", "agency_id": str(ag.id), "score": 0.6}]

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)
    await pq_service.regenerate()

    row = await PopularQuestion.get(text_key=pq_service.normalize_text_key("เกี่ยวกับที่ดิน"))
    assert row.agency_id == ag.id


@pytest.mark.asyncio
async def test_regenerate_resolves_one_of_multiple_agencies(db, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    ag1 = await Agency.create(name="กรมที่ดิน")
    ag2 = await Agency.create(name="กรมการปกครอง")
    await _make_successful_turns(2, agency_ids=[str(ag1.id), str(ag2.id)])

    async def fake_ask_llm(_samples):
        return [{"text": "คำถามรวม", "agency_id": str(ag2.id), "score": 0.7}]

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)
    await pq_service.regenerate()

    row = await PopularQuestion.get(text_key=pq_service.normalize_text_key("คำถามรวม"))
    assert row.agency_id == ag2.id


@pytest.mark.asyncio
async def test_regenerate_drops_out_of_set_agency_id(db, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    await _make_successful_turns(3)  # replies carry no agency

    async def fake_ask_llm(_samples):
        return [{"text": "ไม่มีหน่วยงานตรง", "agency_id": "11111111-1111-1111-1111-111111111111", "score": 0.4}]

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)
    created = await pq_service.regenerate()

    assert created == 1
    row = await PopularQuestion.get(text_key=pq_service.normalize_text_key("ไม่มีหน่วยงานตรง"))
    assert row.agency_id is None


@pytest.mark.asyncio
async def test_regenerate_rejects_real_agency_never_fed(db, monkeypatch):
    """An agency that exists in the DB but was not fed to the LLM is not a valid target."""
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    unfed = await Agency.create(name="หน่วยงานที่ไม่ได้ป้อน")
    await _make_successful_turns(3)  # replies carry no agency, so unfed is absent from samples

    async def fake_ask_llm(_samples):
        return [{"text": "อ้างหน่วยงานที่ไม่ได้ป้อน", "agency_id": str(unfed.id), "score": 0.5}]

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)
    await pq_service.regenerate()

    row = await PopularQuestion.get(text_key=pq_service.normalize_text_key("อ้างหน่วยงานที่ไม่ได้ป้อน"))
    assert row.agency_id is None


@pytest.mark.asyncio
async def test_regenerate_survives_comma_joined_agency_ids(db, monkeypatch):
    """A reply row whose agency_ids holds a single comma-joined element must not
    crash the UUID query; both agencies are still resolved into the sample."""
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    ag1 = await Agency.create(name="กรมที่ดิน")
    ag2 = await Agency.create(name="กรมการปกครอง")
    # Dirty legacy data: three ids collapsed into one string element.
    await _make_successful_turns(2, agency_ids=[f"{ag1.id},{ag2.id}"])

    captured = {}

    async def fake_ask_llm(samples):
        captured["samples"] = samples
        return []

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)

    created = await pq_service.regenerate()

    assert created == 0
    names = {a["name"] for s in captured["samples"] for a in s["agencies"]}
    assert names == {"กรมที่ดิน", "กรมการปกครอง"}


@pytest.mark.asyncio
async def test_regenerate_no_agency_when_reply_has_none(db, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    await _make_successful_turns(3)

    async def fake_ask_llm(_samples):
        return [{"text": "คำถามไม่มีหน่วยงาน", "agency_id": "", "score": 0.5}]

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)
    created = await pq_service.regenerate()

    assert created == 1
    row = await PopularQuestion.get(text_key=pq_service.normalize_text_key("คำถามไม่มีหน่วยงาน"))
    assert row.agency_id is None


@pytest.mark.asyncio
async def test_create_question_persists_manual_source(db):
    pq = await pq_service.create_question(PopularQuestionCreate(text="new q"))

    assert pq.source == PopularQuestionSource.manual
    assert pq.text_key == pq_service.normalize_text_key("new q")


@pytest.mark.asyncio
async def test_create_question_rejects_unknown_agency(db):
    with pytest.raises(HTTPException) as exc:
        await pq_service.create_question(PopularQuestionCreate(text="q", agency_id=uuid.uuid4()))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_question_rejects_duplicate_text_key(db):
    await PopularQuestion.create(text="dup", text_key=pq_service.normalize_text_key("dup"), source="manual")
    with pytest.raises(HTTPException) as exc:
        await pq_service.create_question(PopularQuestionCreate(text="dup"))
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_question_flips_auto_source_to_manual_on_text_change(db):
    pq = await PopularQuestion.create(text="auto q", text_key="auto_q", source="auto")

    updated = await pq_service.update_question(pq.id, PopularQuestionUpdate(text="edited"))

    assert updated.source == PopularQuestionSource.manual
    assert updated.text_key == pq_service.normalize_text_key("edited")


@pytest.mark.asyncio
async def test_update_question_missing_raises_404(db):
    with pytest.raises(HTTPException) as exc:
        await pq_service.update_question(uuid.uuid4(), PopularQuestionUpdate(pinned=True))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_question_removes_row(db):
    pq = await PopularQuestion.create(text="to delete", text_key="to_delete", source="manual")

    await pq_service.delete_question(pq.id)

    assert not await PopularQuestion.filter(id=pq.id).exists()


@pytest.mark.asyncio
async def test_delete_question_missing_raises_404(db):
    with pytest.raises(HTTPException) as exc:
        await pq_service.delete_question(uuid.uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_questions_includes_hidden(db):
    await PopularQuestion.create(text="hidden one", text_key="hidden_one", source="seed", hidden=True)

    rows = await pq_service.list_questions()

    assert len(rows) == 1


@pytest.mark.asyncio
async def test_to_response_resolves_agency(db):
    ag = await Agency.create(name="กรมการปกครอง", logo="🏛️")
    pq = await PopularQuestion.create(text="with agency", text_key="with_agency", source="seed", agency=ag)

    resp = await pq_service.to_response(pq)

    assert resp.agency is not None and resp.agency.id == ag.id


@pytest.mark.asyncio
async def test_seed_is_idempotent(db):
    await Agency.create(name="กรมการปกครอง")
    await Agency.create(name="กรมที่ดิน")
    await Agency.create(name="สำนักงานคณะกรรมการอาหารและยา")

    first = await pq_service.seed_popular_questions()
    second = await pq_service.seed_popular_questions()

    assert first == 6
    assert second == 0
    assert await PopularQuestion.filter(source="seed").count() == 6
