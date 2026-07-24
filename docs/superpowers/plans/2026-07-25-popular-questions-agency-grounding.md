# Popular-Questions Agency Grounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `regenerate()` attach the *real* agency to each auto popular question by feeding each question's known agency into the LLM and resolving the LLM's returned agency **id** exactly, instead of guessing an agency name from text.

**Architecture:** Each chat turn already records the real `agency_ids` on the assistant reply, linked to the question by `parent_id`. `regenerate()` now joins questions to that agency set, feeds `question [agency]` pairs plus an id reference block to the LLM, and asks for an `agency_id` back. The returned id is resolved against the set of agencies actually fed (blocking hallucinated ids); anything else → `None`.

**Tech Stack:** Python 3.12, Tortoise ORM, pytest-asyncio.

## Global Constraints

- Single file of production code: `backend/app/services/popular_questions.py`. No model/schema/migration/frontend changes.
- TDD mandatory: failing test → confirm fail → minimal code → confirm pass.
- Google Python style; American English; imports sorted by path; minimal comments (only non-obvious rationale).
- Run tests with `rtk pytest` from `backend/`.
- Public API output shape (`{id, name, logo}`) and churn/dedupe/tombstone logic must stay unchanged.

---

### Task 1: Ground agency mapping in real turn data

**Files:**
- Modify: `backend/app/services/popular_questions.py` (`_LLM_PROMPT`, `_ask_llm`, `regenerate`; add `_build_samples`, `_format_agency_reference`, `_format_question`)
- Test: `backend/tests/services/test_popular_questions.py`

**Interfaces:**
- Produces:
  - `_build_samples(user_rows: list[dict]) -> list[dict]` — each item `{"text": str, "agencies": list[{"id": str, "name": str}]}`.
  - `_ask_llm(samples: list[dict]) -> list[dict]` — candidate shape `{"text": str, "agency_id": str, "score": float}`.
- Consumes: `Message` (`role`, `parent_id`, `agency_ids`), `Agency` (`id`, `name`), `app.services.llm.chat`.

---

- [ ] **Step 1: Update the test helper to write an assistant reply carrying agency_ids**

Replace `_make_successful_turns` (currently ~line 162) with:

```python
async def _make_successful_turns(n: int, question: str = "คำถามทดสอบ", agency_ids=None) -> None:
    for _ in range(n):
        conv = await Conversation.create(status="success")
        user_msg = await Message.create(conversation=conv, role="user", content=question)
        await Message.create(
            conversation=conv, role="assistant", parent_id=user_msg.id,
            content="ตอบ", agency_ids=agency_ids or [],
        )
```

- [ ] **Step 2: Write the failing feature tests**

Replace the two agency tests (`test_regenerate_resolves_agency_case_insensitively`,
`test_regenerate_leniently_keeps_unmatched_agency`) and add three more, in
`test_popular_questions.py`:

```python
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
```

Also update the three `_ask_llm` robustness tests to the new input and candidate shape:

```python
# test_ask_llm_parses_markdown_fenced_json
content = '```json\n{"questions": [{"text": "คำถาม1", "agency_id": "", "score": 0.5}]}\n```'
result = await pq_service._ask_llm([{"text": "q", "agencies": []}])
assert result == [{"text": "คำถาม1", "agency_id": "", "score": 0.5}]

# test_ask_llm_parses_json_with_leading_prose
content = 'นี่คือคำถามยอดนิยม:\n{"questions": [{"text": "q2", "agency_id": "", "score": 0.3}]}\nขอบคุณครับ'
result = await pq_service._ask_llm([{"text": "q", "agencies": []}])
assert result == [{"text": "q2", "agency_id": "", "score": 0.3}]

# test_ask_llm_returns_empty_on_garbage_output
result = await pq_service._ask_llm([{"text": "q", "agencies": []}])
assert result == []
```

- [ ] **Step 3: Run the new/updated tests — confirm they fail**

Run: `cd backend && rtk pytest tests/services/test_popular_questions.py -q`
Expected: FAIL (`_ask_llm` still takes `list[str]`; `regenerate` still uses `agency` name / `name__iexact`; new tests reference behavior not yet built).

- [ ] **Step 4: Rewrite the prompt and add formatting + sampling helpers**

In `popular_questions.py`, replace `_LLM_PROMPT` with:

```python
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
```

Add these helpers (place near `_ask_llm`):

```python
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
            ids = [str(a) for a in (reply["agency_ids"] or [])]
            agency_ids_by_parent[reply["parent_id"]] = ids
            all_ids.update(ids)
    name_by_id: dict[str, str] = {}
    if all_ids:
        for ag in await Agency.filter(id__in=all_ids).values("id", "name"):
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
```

- [ ] **Step 5: Switch `_ask_llm` to grounded samples**

Replace `_ask_llm`:

```python
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
```

- [ ] **Step 6: Switch `regenerate` to grounded sampling + id resolution**

In `regenerate`, replace the sampling block (the `questions = await Message.filter(... ).values_list("content", flat=True)` and `candidates = await _ask_llm(list(questions))`) with:

```python
    user_rows = await Message.filter(
        role="user", created_at__gte=cutoff, conversation__status="success",
    ).order_by("-created_at").limit(_LLM_QUESTION_SAMPLE).values("id", "content")

    samples = await _build_samples(list(user_rows))
    candidates = await _ask_llm(samples)
    if not candidates:
        return 0
```

Keep the churn delete line unchanged. Immediately after it, build the valid-id map:

```python
    # Only agencies we actually fed the LLM are valid targets — blocks hallucinated ids.
    valid_ids = {a["id"] for s in samples for a in s["agencies"]}
    agency_by_id: dict[str, Agency] = {}
    if valid_ids:
        for ag in await Agency.filter(id__in=valid_ids):
            agency_by_id[str(ag.id)] = ag
```

Inside the candidate loop, replace the agency-name block:

```python
        agency = None
        agency_name = str(cand.get("agency") or "").strip()
        if agency_name:
            agency = await Agency.filter(name__iexact=agency_name).first()
```

with:

```python
        agency = agency_by_id.get(str(cand.get("agency_id") or "").strip())
```

Leave the `text`/`key`/tombstone/`score`/`PopularQuestion.create` lines unchanged.

- [ ] **Step 7: Run the full service test file — confirm green**

Run: `cd backend && rtk pytest tests/services/test_popular_questions.py -q`
Expected: PASS (all tests, including the untouched churn/tombstone/min-turns tests).

- [ ] **Step 8: Run the popular-questions router tests to confirm no contract break**

Run: `cd backend && rtk pytest tests/routers/test_popular_questions_router.py -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
rtk git add backend/app/services/popular_questions.py backend/tests/services/test_popular_questions.py
rtk git commit -m "feat(popular-questions): ground agency mapping in real turn data"
```

---

## Self-Review

**Spec coverage:**
- Sampling join (spec §Design.1) → Step 4 `_build_samples` + Step 6 sampling switch. ✓
- Prompt with agency + id reference, `agency_id` return (spec §Design.2) → Steps 4–5. ✓
- Exact id lookup + validation guard (spec §Design.3) → Step 6 `agency_by_id` + `.get`. ✓
- Multi-agency shows all / picks one (spec) → `_format_question` joins names; `test_regenerate_resolves_one_of_multiple_agencies`. ✓
- No-agency question (spec) → `test_regenerate_no_agency_when_reply_has_none`. ✓
- Out-of-set id → None (spec) → `test_regenerate_drops_out_of_set_agency_id`. ✓
- Unchanged: churn/dedupe/tombstone/public shape → those tests left intact, run in Steps 7–8. ✓

**Placeholder scan:** none — all steps carry concrete code.

**Type consistency:** `_build_samples` produces `{"text", "agencies":[{"id","name"}]}`; `_format_question`/`_format_agency_reference`/`regenerate` all read those exact keys. `_ask_llm` consumes samples, returns candidates keyed `text`/`agency_id`/`score`; `regenerate` reads `agency_id`. Consistent. ✓
