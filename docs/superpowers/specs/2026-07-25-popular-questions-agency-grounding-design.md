# Ground popular-question agency mapping in real turn data

**Date:** 2026-07-25
**Scope:** `backend/app/services/popular_questions.py` + `backend/tests/services/test_popular_questions.py`
**Status:** Approved design, ready for implementation plan

## Problem

`regenerate()` samples only the user message `content` and discards the fact
that each question's real agency is already recorded. It asks the LLM to guess
an agency *name*, then resolves it with `Agency.filter(name__iexact=...)`
(popular_questions.py:120). The LLM's free-text guess rarely matches a DB name
exactly, so the agency comes back `None` or wrong. Agency mapping on
auto-generated popular questions is therefore poor.

## The known-agency link

For every chat turn, the assistant reply stores the real `agency_ids`
(`app/services/chat/turn.py:83`) and points back to the question via
`asst_msg.parent_id = user_msg.id`. Each question already has a grounded agency
set; the fix is to carry it into the prompt instead of making the LLM guess.

Relevant data model facts:

- `Message.agency_ids` (JSON list of agency UUID strings) is populated on the
  **assistant** message, not the user message.
- `Message.parent_id` on the assistant message equals the user message id.
- `Agency` has `id` (UUID), `name`, `logo`.

## Design

All changes are confined to `backend/app/services/popular_questions.py` and its
test file. No model changes, no schema migration, no frontend change.

### 1. Sampling — join question to its agency

Replace the content-only `values_list` (popular_questions.py:97-99) with:

1. Pull recent successful **user** messages (`id`, `content`) within the window,
   newest first, capped at `_LLM_QUESTION_SAMPLE`.
2. Batch-fetch their assistant siblings by `parent_id in {user_ids}` and read
   `agency_ids`.
3. Resolve every referenced agency id to `{id, name}` in a single `Agency`
   query.
4. Build grounded samples: `{"text": <question>, "agencies": [{"id", "name"}, ...]}`.

Rules:

- **Multi-agency question** (assistant reply had >1 agency): include *all*
  involved agencies on that sample; the LLM picks the single most relevant.
- **No agency** (no assistant reply, or empty `agency_ids`): the sample carries
  an empty `agencies` list.

The min-turns cold-start guard stays as-is, counting recent successful user
messages.

### 2. Prompt — feed the agency, ask for an id back

Each question line becomes:

```
- <question text>  [หน่วยงาน: กรมที่ดิน]
```

(Multiple agencies are comma-joined; none omits the bracket or leaves it empty.)

The prompt also includes a compact reference block listing every agency present
in this batch:

```
หน่วยงานอ้างอิง:
กรมที่ดิน = <uuid>
กรมการปกครอง = <uuid>
```

The LLM is instructed to return, per canonical question:

```json
{"questions": [{"text": "<คำถาม>", "agency_id": "<uuid หรือค่าว่าง>", "score": <0.0-1.0>}]}
```

choosing `agency_id` **only** from the provided reference ids, or empty when no
agency applies.

### 3. Mapping — exact id lookup, validated

`_ask_llm` returns candidates whose agency key is `agency_id` (was `agency`).
In `regenerate()`:

- Build an `{id: Agency}` map from the grounded sample set.
- Attach the agency by exact id lookup in that map.
- **Validation guard:** accept the returned `agency_id` only if it exists in
  the known set; otherwise set `agency = None`.

This removes the `name__iexact` fragility and blocks hallucinated ids, keeping
every auto popular-question agency tied to real usage.

`_ask_llm` signature changes from `list[str]` to the grounded sample list.

## Out of scope / unchanged

- Churn / dedupe / tombstone logic in `regenerate()`.
- `normalize_text_key`, `published_questions`, `_extract_json_payload`.
- Public API output shape (`{id, name, logo}`).
- `seed_popular_questions` (seeded agencies are already correct).
- Models, DB schema, frontend.

## Testing (TDD)

Update `backend/tests/services/test_popular_questions.py`:

- Extend the `_make_successful_turns` helper to also create an assistant reply
  with `agency_ids`, so samples carry a real agency.
- **Correct agency by id:** a question whose paired reply has a known
  `agency_id` gets that `Agency` attached (by id).
- **Out-of-set / hallucinated id:** LLM returns an `agency_id` not in the batch
  set → `agency` is `None`, row still created. (Replaces the old
  case-insensitive-name resolution test.)
- **No agency:** question with empty `agency_ids` → no agency, row still created.
- **Multi-agency:** reply with several `agency_ids` → the LLM-chosen id resolves
  correctly.
- Update the existing `_ask_llm` JSON-robustness and regenerate tests to the new
  `agency_id` candidate shape and the new `_ask_llm` input signature.

Follow red → green → refactor for each behavior.
