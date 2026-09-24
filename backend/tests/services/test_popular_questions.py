"""Tests for app.features.analytics.services.popular_questions."""
import uuid

import pytest

from app.core.errors import ApiError
from app.features.analytics.models.popular_question import PopularQuestionSource
from app.features.agency.repositories import agency as agency_repo
from app.features.chat.repositories import conversation as conversation_repo
from app.features.chat.repositories import message as message_repo
from app.features.analytics.repositories import popular_question as pq_repo
from app.features.analytics.schemas.popular_question import PopularQuestionCreate, PopularQuestionUpdate
from app.features.analytics.services import popular_questions as pq_service
from app.features.llm.services.errors import LlmError
from app.features.llm.services.result_schemas import PopularQuestionItem, PopularQuestionsResult


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


async def test_published_excludes_hidden(db_session):
    await pq_repo.create(db_session, text="visible", text_key="visible", source="seed", hidden=False)
    await pq_repo.create(db_session, text="secret", text_key="secret", source="seed", hidden=True)

    rows = await pq_service.published_questions(db_session)

    assert [r["text"] for r in rows] == ["visible"]


async def test_published_pinned_first(db_session):
    await pq_repo.create(db_session, text="unpinned", text_key="unpinned", source="seed", pinned=False)
    await pq_repo.create(db_session, text="pinned", text_key="pinned", source="seed", pinned=True)

    rows = await pq_service.published_questions(db_session)

    assert rows[0]["text"] == "pinned"


async def test_published_orders_by_sort_order_within_pinned(db_session):
    await pq_repo.create(db_session, text="second", text_key="second", source="seed", pinned=True, sort_order=2)
    await pq_repo.create(db_session, text="first", text_key="first", source="seed", pinned=True, sort_order=1)

    rows = await pq_service.published_questions(db_session)

    assert [r["text"] for r in rows] == ["first", "second"]


async def test_published_orders_by_score_desc_nulls_last(db_session):
    await pq_repo.create(db_session, text="no_score", text_key="no_score", source="seed", score=None)
    await pq_repo.create(db_session, text="high", text_key="high", source="seed", score=0.9)
    await pq_repo.create(db_session, text="low", text_key="low", source="seed", score=0.1)

    rows = await pq_service.published_questions(db_session)

    assert [r["text"] for r in rows] == ["high", "low", "no_score"]


async def test_published_falls_back_to_recency(db_session):
    older = await pq_repo.create(db_session, text="older", text_key="older", source="seed")
    newer = await pq_repo.create(db_session, text="newer", text_key="newer", source="seed")
    await db_session.flush()
    older.created_at = newer.created_at.replace(year=newer.created_at.year - 1)
    await db_session.flush()

    rows = await pq_service.published_questions(db_session)

    assert [r["text"] for r in rows] == ["newer", "older"]


async def test_published_caps_at_display_count(db_session, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_DISPLAY_COUNT", 2)
    for i in range(5):
        await pq_repo.create(db_session, text=f"q{i}", text_key=f"q{i}", source="seed")

    rows = await pq_service.published_questions(db_session)

    assert len(rows) == 2


async def test_published_resolves_agency(db_session):
    ag = await agency_repo.create(db_session, name="กรมการปกครอง", logo="🏛️")
    await pq_repo.create(db_session, text="with agency", text_key="with_agency", source="seed", agency_id=ag.id)
    await pq_repo.create(db_session, text="no agency", text_key="no_agency", source="seed")

    rows = await pq_service.published_questions(db_session)
    by_text = {r["text"]: r for r in rows}

    assert by_text["with agency"]["agency"] == {"id": str(ag.id), "name": "กรมการปกครอง", "logo": "🏛️"}
    assert by_text["no agency"]["agency"] is None


async def test_ask_llm_maps_structured_result_to_dicts(db_session, monkeypatch):
    async def fake_parse(session, purpose, messages=None, **_kwargs):
        return PopularQuestionsResult(questions=[
            PopularQuestionItem(text="คำถาม1", agency_id="", score=0.5),
        ])

    monkeypatch.setattr("app.features.llm.services.parse", fake_parse)

    result = await pq_service._ask_llm(db_session, [{"text": "q", "agencies": []}])

    assert result == [{"text": "คำถาม1", "agency_id": "", "score": 0.5}]


async def test_ask_llm_returns_empty_on_llm_error(db_session, monkeypatch):
    async def fake_parse(session, purpose, messages=None, **_kwargs):
        raise LlmError("no enabled binding", kind="config")

    monkeypatch.setattr("app.features.llm.services.parse", fake_parse)

    result = await pq_service._ask_llm(db_session, [{"text": "q", "agencies": []}])

    assert result == []


async def _make_successful_turns(session, n: int, question: str = "คำถามทดสอบ", agency_ids=None) -> None:
    for _ in range(n):
        conv = await conversation_repo.create(session, status="success")
        user_msg = await message_repo.create(session, conversation_id=conv.id, role="user", content=question)
        await message_repo.create(
            session, conversation_id=conv.id, role="assistant", parent_id=user_msg.id,
            content="ตอบ", agency_ids=agency_ids or [],
        )
    await session.flush()


async def test_regenerate_noop_below_min_turns(db_session, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 20)
    await _make_successful_turns(db_session, 5)
    seed = await pq_repo.create(db_session, text="seed q", text_key="seed_q", source="seed")

    called = False

    async def fake_ask_llm(session, _questions):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)

    created = await pq_service.regenerate(db_session)

    assert created == 0
    assert called is False
    assert await pq_repo.by_id(db_session, seed.id) is not None


async def test_regenerate_deletes_unpinned_unhidden_auto_rows_and_inserts_fresh(db_session, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    await _make_successful_turns(db_session, 3)
    stale = await pq_repo.create(db_session, text="stale auto", text_key="stale_auto", source="auto")

    async def fake_ask_llm(session, _questions):
        return [{"text": "new auto question", "agency": "", "score": 0.7}]

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)

    created = await pq_service.regenerate(db_session)

    assert created == 1
    assert await pq_repo.by_id(db_session, stale.id) is None
    assert await pq_repo.text_key_exists(db_session, pq_service.normalize_text_key("new auto question"))


async def test_regenerate_preserves_pinned_auto_row(db_session, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    await _make_successful_turns(db_session, 3)
    pinned = await pq_repo.create(db_session, text="pinned auto", text_key="pinned_auto", source="auto", pinned=True)

    async def fake_ask_llm(session, _questions):
        return []

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)

    await pq_service.regenerate(db_session)

    assert await pq_repo.by_id(db_session, pinned.id) is not None


async def test_regenerate_never_touches_manual_or_seed_rows(db_session, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    await _make_successful_turns(db_session, 3)
    manual = await pq_repo.create(db_session, text="manual q", text_key="manual_q", source="manual")
    seed = await pq_repo.create(db_session, text="seed q", text_key="seed_q", source="seed")

    async def fake_ask_llm(session, _questions):
        return []

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)

    await pq_service.regenerate(db_session)

    assert await pq_repo.by_id(db_session, manual.id) is not None
    assert await pq_repo.by_id(db_session, seed.id) is not None


async def test_regenerate_skips_candidate_matching_hidden_tombstone(db_session, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    await _make_successful_turns(db_session, 3)
    key = pq_service.normalize_text_key("ห้ามกลับมาอีก")
    await pq_repo.create(db_session, text="ห้ามกลับมาอีก", text_key=key, source="auto", hidden=True)

    async def fake_ask_llm(session, _questions):
        return [{"text": "ห้ามกลับมาอีก", "agency": "", "score": 0.5}]

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)

    created = await pq_service.regenerate(db_session)

    assert created == 0
    rows = await pq_repo.all_with_agency(db_session)
    assert len([r for r in rows if r.text_key == key]) == 1


async def test_regenerate_feeds_known_agency_to_llm_and_resolves(db_session, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    ag = await agency_repo.create(db_session, name="กรมที่ดิน")
    await _make_successful_turns(db_session, 2, question="ขอคัดโฉนด", agency_ids=[str(ag.id)])

    captured = {}

    async def fake_parse(session, purpose, messages=None, **kwargs):
        captured["prompt"] = messages[0]["content"]
        return PopularQuestionsResult(questions=[
            PopularQuestionItem(text="ขอคัดโฉนดที่ดิน", agency_id=str(ag.id), score=0.8),
        ])

    monkeypatch.setattr("app.features.llm.services.parse", fake_parse)

    await pq_service.regenerate(db_session)

    assert "กรมที่ดิน" in captured["prompt"]
    assert str(ag.id) in captured["prompt"]
    key = pq_service.normalize_text_key("ขอคัดโฉนดที่ดิน")
    rows = [r for r in await pq_repo.all_with_agency(db_session) if r.text_key == key]
    assert rows[0].agency_id == ag.id


async def test_regenerate_resolves_agency_by_id(db_session, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    ag = await agency_repo.create(db_session, name="กรมที่ดิน")
    await _make_successful_turns(db_session, 3, agency_ids=[str(ag.id)])

    async def fake_ask_llm(session, _samples):
        return [{"text": "เกี่ยวกับที่ดิน", "agency_id": str(ag.id), "score": 0.6}]

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)
    await pq_service.regenerate(db_session)

    key = pq_service.normalize_text_key("เกี่ยวกับที่ดิน")
    rows = [r for r in await pq_repo.all_with_agency(db_session) if r.text_key == key]
    assert rows[0].agency_id == ag.id


async def test_regenerate_resolves_one_of_multiple_agencies(db_session, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    ag1 = await agency_repo.create(db_session, name="กรมที่ดิน")
    ag2 = await agency_repo.create(db_session, name="กรมการปกครอง")
    await _make_successful_turns(db_session, 2, agency_ids=[str(ag1.id), str(ag2.id)])

    async def fake_ask_llm(session, _samples):
        return [{"text": "คำถามรวม", "agency_id": str(ag2.id), "score": 0.7}]

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)
    await pq_service.regenerate(db_session)

    key = pq_service.normalize_text_key("คำถามรวม")
    rows = [r for r in await pq_repo.all_with_agency(db_session) if r.text_key == key]
    assert rows[0].agency_id == ag2.id


async def test_regenerate_drops_out_of_set_agency_id(db_session, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    await _make_successful_turns(db_session, 3)  # replies carry no agency

    async def fake_ask_llm(session, _samples):
        return [{"text": "ไม่มีหน่วยงานตรง", "agency_id": "11111111-1111-1111-1111-111111111111", "score": 0.4}]

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)
    created = await pq_service.regenerate(db_session)

    assert created == 1
    key = pq_service.normalize_text_key("ไม่มีหน่วยงานตรง")
    rows = [r for r in await pq_repo.all_with_agency(db_session) if r.text_key == key]
    assert rows[0].agency_id is None


async def test_regenerate_rejects_real_agency_never_fed(db_session, monkeypatch):
    """An agency that exists in the DB but was not fed to the LLM is not a valid target."""
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    unfed = await agency_repo.create(db_session, name="หน่วยงานที่ไม่ได้ป้อน")
    await _make_successful_turns(db_session, 3)  # replies carry no agency, so unfed is absent from samples

    async def fake_ask_llm(session, _samples):
        return [{"text": "อ้างหน่วยงานที่ไม่ได้ป้อน", "agency_id": str(unfed.id), "score": 0.5}]

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)
    await pq_service.regenerate(db_session)

    key = pq_service.normalize_text_key("อ้างหน่วยงานที่ไม่ได้ป้อน")
    rows = [r for r in await pq_repo.all_with_agency(db_session) if r.text_key == key]
    assert rows[0].agency_id is None


async def test_regenerate_survives_comma_joined_agency_ids(db_session, monkeypatch):
    """A reply row whose agency_ids holds a single comma-joined element must not
    crash the UUID query; both agencies are still resolved into the sample."""
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    ag1 = await agency_repo.create(db_session, name="กรมที่ดิน")
    ag2 = await agency_repo.create(db_session, name="กรมการปกครอง")
    # Dirty legacy data: three ids collapsed into one string element.
    await _make_successful_turns(db_session, 2, agency_ids=[f"{ag1.id},{ag2.id}"])

    captured = {}

    async def fake_ask_llm(session, samples):
        captured["samples"] = samples
        return []

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)

    created = await pq_service.regenerate(db_session)

    assert created == 0
    names = {a["name"] for s in captured["samples"] for a in s["agencies"]}
    assert names == {"กรมที่ดิน", "กรมการปกครอง"}


async def test_regenerate_no_agency_when_reply_has_none(db_session, monkeypatch):
    monkeypatch.setattr(pq_service.settings, "POPULAR_QUESTIONS_MIN_TURNS", 1)
    await _make_successful_turns(db_session, 3)

    async def fake_ask_llm(session, _samples):
        return [{"text": "คำถามไม่มีหน่วยงาน", "agency_id": "", "score": 0.5}]

    monkeypatch.setattr(pq_service, "_ask_llm", fake_ask_llm)
    created = await pq_service.regenerate(db_session)

    assert created == 1
    key = pq_service.normalize_text_key("คำถามไม่มีหน่วยงาน")
    rows = [r for r in await pq_repo.all_with_agency(db_session) if r.text_key == key]
    assert rows[0].agency_id is None


async def test_create_question_persists_manual_source(db_session):
    pq = await pq_service.create_question(db_session, PopularQuestionCreate(text="new q"))

    assert pq.source == PopularQuestionSource.manual
    assert pq.text_key == pq_service.normalize_text_key("new q")


async def test_create_question_rejects_unknown_agency(db_session):
    with pytest.raises(ApiError) as exc:
        await pq_service.create_question(db_session, PopularQuestionCreate(text="q", agency_id=uuid.uuid4()))
    assert exc.value.status == 404


async def test_create_question_rejects_duplicate_text_key(db_session):
    await pq_repo.create(db_session, text="dup", text_key=pq_service.normalize_text_key("dup"), source="manual")
    with pytest.raises(ApiError) as exc:
        await pq_service.create_question(db_session, PopularQuestionCreate(text="dup"))
    assert exc.value.status == 409


async def test_update_question_flips_auto_source_to_manual_on_text_change(db_session):
    pq = await pq_repo.create(db_session, text="auto q", text_key="auto_q", source="auto")

    updated = await pq_service.update_question(db_session, pq.id, PopularQuestionUpdate(text="edited"))

    assert updated.source == PopularQuestionSource.manual
    assert updated.text_key == pq_service.normalize_text_key("edited")


async def test_update_question_missing_raises_404(db_session):
    with pytest.raises(ApiError) as exc:
        await pq_service.update_question(db_session, uuid.uuid4(), PopularQuestionUpdate(pinned=True))
    assert exc.value.status == 404


async def test_delete_question_removes_row(db_session):
    pq = await pq_repo.create(db_session, text="to delete", text_key="to_delete", source="manual")

    await pq_service.delete_question(db_session, pq.id)
    await db_session.flush()

    assert await pq_repo.by_id(db_session, pq.id) is None


async def test_delete_question_missing_raises_404(db_session):
    with pytest.raises(ApiError) as exc:
        await pq_service.delete_question(db_session, uuid.uuid4())
    assert exc.value.status == 404


async def test_list_questions_includes_hidden(db_session):
    await pq_repo.create(db_session, text="hidden one", text_key="hidden_one", source="seed", hidden=True)

    rows = await pq_service.list_questions(db_session)

    assert len(rows) == 1


async def test_to_response_resolves_agency(db_session):
    ag = await agency_repo.create(db_session, name="กรมการปกครอง", logo="🏛️")
    pq = await pq_repo.create(db_session, text="with agency", text_key="with_agency", source="seed", agency_id=ag.id)

    resp = await pq_service.to_response(db_session, pq)

    assert resp.agency is not None and resp.agency.id == ag.id


async def test_seed_is_idempotent(db_session):
    await agency_repo.create(db_session, name="กรมการปกครอง")
    await agency_repo.create(db_session, name="กรมที่ดิน")
    await agency_repo.create(db_session, name="สำนักงานคณะกรรมการอาหารและยา")

    first = await pq_service.seed_popular_questions(db_session)
    second = await pq_service.seed_popular_questions(db_session)

    assert first == 6
    assert second == 0
    rows = await pq_repo.all_with_agency(db_session)
    assert len([r for r in rows if r.source == "seed"]) == 6
