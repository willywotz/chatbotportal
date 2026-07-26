# Persist agent-step / pipeline progress and show it in history

**Date:** 2026-07-26
**Status:** Approved (design)
**Branch:** `feat/persist-agent-steps` (off `refactor/shared-assistant-message-content`, which
introduces `AssistantMessageContent`)

## Problem

The AI-agent pipeline progress — pipeline steps (discover / classify / invoke / verify /
synthesize) with timings, per-agency statuses (passed / rejected / error), and errors — is shown
live during a chat via `StreamingProgress`, but it is **ephemeral**. The backend `Message` model has
an `agent_steps` JSON field, yet nothing ever populates it: the pipeline events are streamed to the
client over `/chat/stream` and then dropped before the assistant message is saved. History
(`/history/{id}` and `/history/{id}/messages`) therefore always returns `agent_steps: []`, and the
`/history` UI cannot show how an answer was produced.

## Goal

Persist a snapshot of the pipeline progress with each assistant message and render it as its own
collapsible card, shared by both live chat (`MessageBubble`) and history (`MessageItem`) via the
shared `AssistantMessageContent` component.

## Decisions

- **Storage:** reuse the existing `Message.agent_steps` JSON field — no DB migration; history already
  returns it.
- **Data scope:** full snapshot — pipeline steps + per-agency statuses + errors.
- **Errors:** stored **inside** the snapshot (single field feeds the card on both paths), not read
  from the separate `Message.errors`.
- **Card behavior:** collapsible, **collapsed by default** (like the Thinking panel).
- **Card order in the message stack:** **Thinking → answer bubble → Summary → Agent steps**
  (agent-steps card is last).
- **Path coverage:** `/chat/stream` (the SSE path the portal uses) only. The OpenAI-compatible
  Responses API keeps dropping pipeline events (out of scope).

## Data shape

Persisted in `Message.agent_steps` as one object, or `[]` / null when nothing was captured
(e.g. cached replays). Snake_case to match backend convention; the frontend normalizes to camelCase.

```jsonc
{
  "steps": [
    { "name": "discover", "ms": 1200 },
    { "name": "invoke",   "ms": 3400 }
  ],
  "agencies": [
    { "id": "land", "name": "กรมที่ดิน", "status": "passed",
      "error_type": null, "relevance_score": 0.9, "section_label": "ค่าธรรมเนียม" }
  ],
  "errors": [
    { "agency": "foo", "name": "Foo", "error_type": "timeout", "message": "..." }
  ]
}
```

`status` for an agency is the terminal state: `ok` / `error` from `agency_responded`, upgraded to
`passed` / `rejected` by `agency_verified`.

## Backend (`/chat/stream` only)

Files: `backend/app/services/chat/stream.py`, `backend/app/services/chat/turn.py`,
`backend/app/models/conversation.py` (model unchanged — field already exists).

1. **Pure accumulator** — a new helper (e.g. `build_pipeline_snapshot()` or a small folding class in
   a new `backend/app/services/chat/pipeline_snapshot.py`) that folds the streamed events into the
   snapshot above:
   - `step` events → `steps[]` (keep terminal/`done` steps with their `ms`).
   - `agency_start` → seed an agency entry; `agency_responded` → set `ok`/`error` + `error_type`;
     `agency_verified` → upgrade to `passed`/`rejected` + `relevance_score`.
   - `errors` come from `answer_data["errors"]` at persist time.
   This mirrors the frontend reducer in `useChatStream`.
2. **`_stream_live`** folds each non-`answer`/`done` event into the accumulator, then passes the
   final snapshot to `_persist`.
3. **`_persist` / `save_turn`** gain an `agent_steps` parameter forwarded to `Message.create`.
4. **Cached replays** (`_replay_cached`): no fresh snapshot (empty) — they reuse a prior answer.

## Frontend

Files: `frontend/src/shared/types/chat.ts`, `frontend/src/shared/types/conversation.ts`,
`frontend/src/shared/components/AssistantMessageContent.tsx`, a new
`frontend/src/shared/components/AgentStepsCard.tsx`, a new normalizer (e.g.
`frontend/src/shared/lib/agentSteps.ts`), `frontend/src/features/chat/MessageBubble.tsx`,
`frontend/src/features/history/MessageItem.tsx`, and the live capture in
`frontend/src/features/chat/useChat.ts` / `useChatStream.ts`.

1. **Type** `AgentStepsSnapshot` (camelCase) in `shared/types/chat.ts`:
   ```ts
   interface AgentStepsSnapshot {
     steps: { name: string; ms: number | null }[];
     agencies: {
       id: string; name: string | null; status: AgencyStatus;
       errorType?: string | null; relevanceScore?: number | null; sectionLabel?: string | null;
     }[];
     errors: { agency: string; name: string; errorType: string; message: string }[];
   }
   ```
   Retype `ChatMessage.agentSteps` to `AgentStepsSnapshot | undefined`.
2. **Normalizer** `toAgentStepsSnapshot(raw): AgentStepsSnapshot | null` — snake→camel, tolerant of
   `[]` / null / missing; returns `null` when there is nothing to show (no steps, agencies, or
   errors). Pure, unit-tested.
3. **`AgentStepsCard`** — a static, collapsible card (collapsed by default, Thinking-panel styling):
   pipeline steps with durations + ✓, per-agency statuses with their icons, and errors. Terminal
   state only (no running/pulse states). Renders nothing when passed `null`.
4. **`AssistantMessageContent`** gains a `steps?: AgentStepsSnapshot | null` prop and renders
   `<AgentStepsCard steps={steps} />` **after** the summary card. Order:
   Thinking → answer bubble → Summary → Agent steps.
5. **Call sites:** `MessageBubble` passes `steps={message.agentSteps}`; `MessageItem` passes
   `steps={toAgentStepsSnapshot(msg.agent_steps)}`.
6. **Live attach:** on the `done` event, build an `AgentStepsSnapshot` from the terminal
   `StreamingState` (`pipelineSteps`, `agencyStatuses`, `errors`) and set it on the completed
   `ChatMessage.agentSteps`, so a just-finished live message shows the card without a refetch.

The live `StreamingProgress` typing indicator in `ChatConversation` is unchanged — it remains the
in-progress view; `AgentStepsCard` is the persisted after-the-fact view.

## Testing (TDD, both stacks)

**Backend (pytest):**
- Unit-test the accumulator: a representative event sequence → expected snapshot (agency
  `ok`→`passed` upgrade, `error` + `error_type`, step timings).
- Integration test: a streamed turn persists a populated `agent_steps`; history returns it.

**Frontend (vitest):**
- `toAgentStepsSnapshot`: snake→camel mapping; empty/`[]`/null → `null`.
- `AgentStepsCard`: renders steps/agencies/errors; collapsed by default, expands on click; renders
  nothing for `null`.
- `AssistantMessageContent`: shows the card when `steps` present, hides when absent; card sits after
  the summary.

## Out of scope

- OpenAI-compatible Responses API pipeline persistence.
- Backfilling `agent_steps` for historical messages saved before this change.
- Changing the live `StreamingProgress` indicator.
