# Merge `MessageBubble` + `MessageItem` into a shared `Message`

## Problem

Two components render a chat message and have drifted despite showing the same
thing:

- `src/features/chat/MessageBubble.tsx` — live chat. Consumes `ChatMessage`
  (camelCase). Renders rating buttons + `FeedbackDialog`, source chips, and a
  timestamp. Memoized.
- `src/features/history/MessageItem.tsx` — history dialog. Consumes
  `ConversationMessage` (snake_case). Renders none of rating/sources/timestamp,
  with a smaller user bubble.

Both already delegate the assistant reply to the shared
`AssistantMessageContent`, so the divergence is the surrounding shell, the extra
chat features, and the two field-naming conventions.

Only three fields actually differ by name between the two types:

| Concept      | `ChatMessage`        | `ConversationMessage`                   |
| ------------ | -------------------- | --------------------------------------- |
| summary refs | `summaryReferences`  | `summary_references`                    |
| agent steps  | `pipeline` (snapshot)| `agent_steps` (raw → `toAgentStepsSnapshot`) |
| timestamp    | `timestamp`          | `created_at`                            |

`id`, `role`, `content`, `summary`, `sources`, and `rating` already align.

## Decisions

- **Unify + enrich history.** One shared component. History now also renders
  read-only source chips and a timestamp (the data already exists on
  `ConversationMessage`), but still shows **no** rating buttons.
- **Normalized prop + adapters.** The component consumes a single
  `DisplayMessage` shape. Each call site maps its own type via a tiny adapter,
  so the component knows only one convention.
- **Component name:** `Message`.

## Design

### 1. Shared component — `src/shared/components/Message.tsx`

- `memo`-wrapped (carried over from `MessageBubble`).
- Props: `{ message: DisplayMessage; onRate?: (id, rating, feedbackText?) => void }`.
- Assistant → `AssistantMessageContent`; user → plain bubble.
- **Rating buttons + `FeedbackDialog`:** rendered only when `onRate` is passed.
  Chat passes it; history omits it → no rating UI in history.
- **Source chips:** rendered whenever `message.sources?.length`. Now shows in
  both chat and history.
- **Timestamp:** rendered whenever `message.timestamp`. Now shows in both.
- **Styling unified on the chat version:** outer `flex gap-3 mb-4` with
  `flex-row-reverse` for user; user bubble
  `rounded-2xl rounded-tr-sm bg-primary px-4 py-3 text-[1em] leading-relaxed
  text-primary-foreground`. History's smaller `rounded-lg … text-sm` bubble is
  dropped. Verify spacing inside `ConversationDetailDialog` does not double up.

### 2. Normalized shape — `src/shared/types`

```ts
interface DisplayMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  summary?: string | null;
  summaryReferences?: SummaryReference[];
  steps?: AgentStepsSnapshot | null;
  sources?: { agency: string; url: string; title: string }[];
  rating?: 'up' | 'down' | null;
  timestamp?: string;
}
```

### 3. Adapters (co-located with each source type)

- `chatMessageToDisplay(m: ChatMessage): DisplayMessage` — maps `pipeline → steps`,
  passes the rest through.
- `conversationMessageToDisplay(m: ConversationMessage): DisplayMessage` — maps
  `summary_references → summaryReferences`, `toAgentStepsSnapshot(agent_steps) →
  steps`, `created_at → timestamp`, coerces `sources` to the typed shape.

### 4. Call sites

- `ChatConversation.tsx`:
  `<Message message={chatMessageToDisplay(msg)} onRate={onRate} />`
- `ConversationDetailDialog.tsx`:
  `<Message message={conversationMessageToDisplay(msg)} />`

### 5. Deletions

- `src/features/chat/MessageBubble.tsx`
- `src/features/history/MessageItem.tsx`

## Testing (TDD)

Three existing tests reference the old components:
`MessageBubbleSummary.test.tsx`, `MessageItem.test.tsx`, `chatRatingFlow.test.tsx`.

- Retarget them at `Message` + the adapters.
- Add coverage that history (no `onRate`) renders source chips + timestamp but
  **no** rating buttons.
- Keep chat coverage: rating flow, summary rendering.
- Red → green confirmed for each change.

## Out of scope

- Backend/type changes to `ChatMessage` / `ConversationMessage` themselves.
- Any redesign of `AssistantMessageContent`, `SummaryCard`, or `AgentStepsCard`.
