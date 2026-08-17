# OneChat v5 migration — design

Date: 2026-07-21
Source spec: `spec/v5.md` (upstream OneChat API contract)
Branch: `feat/onechat-v5` (off `dev`)

## Goal

Move the portal's streaming chat proxy (`POST /api/v1/chat/stream`) from OneChat **v4** to
**v5**, surfacing the three things v5 adds, and keep a no-redeploy rollback to v4.

What v5 adds over v4 (upstream, `spec/v5.md`):

| Addition | Where |
|---|---|
| `summarize` pipeline step | new `step` event between `verify` and `synthesize` |
| `summary` — LLM executive summary with `[n]` citations | `answer` event |
| `references[]` — one entry per agency, scoped to the summary only | `answer` event |
| `thread_name` — short LLM-generated conversation name | `intent` and `done` events |

`sections[]` are byte-identical to v4 and carry **no** `[n]` markers. When summary generation
fails upstream, v5 degrades silently: `summary`/`references` are empty and `answer` equals what
v4 would have returned (spec §4.3). `thread_name` is `null` when upstream has no `REDIS_URL`.

## Decisions

1. **Full migration**, frontend included — not a passthrough.
2. **Configurable, default v5.** `CHAT_STREAM_VERSION` selects the upstream; flipping it to
   `v4` at `/settings` is the rollback.
3. **Distinct summary card** in the chat UI, above the raw sections — not a plain
   markdown dump of the composed `answer`.
4. **`thread_name` becomes the conversation title** on the first turn.
5. **Two new `messages` columns** (`summary`, `summary_references`); `sources` keeps its
   existing section-derived meaning. The column is *not* named `references` — that is a
   reserved SQL keyword in Postgres and would need quoting at every use site.

## Backend

### Config (`app/config.py`)

- `ONECHAT_V5_URL: str = "http://185.84.160.55:8000/v5/chat"`, added to the `"OneChat"` group in
  `SETTINGS_GROUPS` so it is editable from `/settings`.
- `CHAT_STREAM_VERSION: str = "v5"` — `"v4" | "v5"`. Resolved per request; unknown values fall
  back to `v5` with a logged warning. `ONECHAT_V4_URL` stays for rollback.

### Stream proxy (`routers/chat.py::chat_stream`)

- Resolve the upstream URL from `CHAT_STREAM_VERSION`. Error messages and
  `ConnectionLog.connection_type` (`external_chat_v4` / `external_chat_v5`) follow the selected
  version rather than being hardcoded to v4.
- `summarize` needs no relay code — the existing loop forwards any `step` event verbatim.
- Capture `thread_name` from the `done` event alongside `session_id` / `total_ms`, and keep
  forwarding `done` with the portal's own `conversation_id` and `message_id` merged in.

### Persistence

- Migration generated with `aerich migrate` (never hand-authored, never hand-carry
  `MODELS_STATE` — see `docs/aerich-migrations.md`) adding to `messages`:
  - `summary TEXT NULL`
  - `summary_references JSONB NOT NULL DEFAULT '[]'`
- `save_turn()` gains `summary: str | None` and `summary_references: list | None`, written to the
  assistant message only. Both default to empty, so v4 mode and the degrade case write nothing
  new and behave exactly as today.
- `_save_stream_conversation()` reads the `summary` / `references` fields off the `answer` event
  and passes them through. Upstream's SSE field stays `references`; ours is `summary_references`
  from the model layer outward.
- **Title from `thread_name`:** only when the conversation is being *created* (first turn) and
  `thread_name` is non-null → `title = thread_name[:TITLE_MAX_LENGTH]`. Otherwise the existing
  `query`-derived title stands. Upstream already pins the name after turn 1, so later turns are
  ignored regardless.
- **Similarity-cache replay** emits the stored `summary` / `references` in its synthetic `answer`
  event, so a cache hit renders identically to a live v5 turn.
- `GET /conversations/{id}` message payloads gain `summary` and `summary_references` so reloaded
  history renders the summary card.

Sync `POST /chat` (OneChat v3) is untouched — v5 defines no sync endpoint.

## Frontend

### Types (`shared/types/chat.ts`)

- `PipelineStepName` gains `'summarize'`.
- `IntentEvent` and `DoneEvent` gain `thread_name: string | null`.
- `AnswerEvent` gains `summary: string` and
  `references: { number: number; agency_id: string; agency_name: string; url: string | null }[]`.
- `StreamingState` gains `summary`, `summaryReferences`, `threadName`.
- `ChatMessage` gains optional `summary` and `summaryReferences`, so live streaming and reloaded
  history render through one path.

### Rendering

- `STEP_LABELS.summarize = { icon: '📌', label: 'สรุปภาพรวม' }` — the progress list picks it up.
- New `SummaryCard` component: markdown-rendered `summary` followed by the numbered
  `references[]` (agency name only; `url` is always `null` today, so no links yet).
- **Avoiding duplication.** Upstream's `answer` already contains
  `summary` → reference list → `---` → sections. Rendering the card *and* the full `answer` would
  show the summary twice. A pure helper `stripSummaryPrefix(content, summary)` returns the body:
  if `summary` is non-empty and `content` starts with it, return everything after the first `---`
  divider; otherwise return `content` unchanged. `MessageBubble` renders `SummaryCard` plus the
  stripped body. With no summary (v4 mode, degrade, smart fallback) the helper is a no-op and the
  bubble is identical to today's.

## Testing (TDD — failing test first, every step)

Backend (pytest, `backend/tests/`):
- `CHAT_STREAM_VERSION` selects the correct upstream URL; unknown value falls back to v5.
- `summary` / `references` from the `answer` event are persisted on the assistant message.
- `thread_name` sets the conversation title on turn 1 only; `null` leaves the query-derived title.
- Degrade case (no `summary` in the `answer` event) writes empty values and produces a turn
  indistinguishable from v4.
- Cache replay re-emits the stored summary and references.

Frontend (vitest):
- `applyStepEvent` handles `summarize`; `applyAnswerEvent` stores `summary` / `summaryReferences`.
- `stripSummaryPrefix`: prefix present, prefix absent, no divider, `---` inside agency content.
- `SummaryCard` renders summary text and numbered references.
- `MessageBubble` does not duplicate the summary.

## Rollout

- Branch `feat/onechat-v5` off `dev`; PR into `dev`.
- Rollback: set `CHAT_STREAM_VERSION=v4` at `/settings` — no redeploy, no data migration back.
- On merge to `main`: update `CONTEXT.md` and rebuild docker compose.

## Out of scope

- v5 sync endpoint (does not exist upstream).
- Linking `references[].url` (always `null` in the current contract).
- Any change to in-process agency dispatch (`services/chat/dispatch.py`).
