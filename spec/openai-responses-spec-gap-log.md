# Is `openai-responses.md` sufficient to regenerate the implementation?

**Verdict:** Yes for *behaviour* — a from-scratch rebuild of the responses layer, driven only
by `spec/openai-responses.md`, produces **byte-identical wire output on 25/25 scenarios** across
HTTP, SSE and WebSocket. **But** eight of those matches were only reachable because the builder
resolved an ambiguity by reading the code. A strictly blind, spec-only build would have drifted
on all eight until corrected. The spec is a complete *output* contract; it is **not** a complete
*build* contract, because it omits the upstream `ChatEvent` **input** vocabulary the translation
layer consumes.

## Method

- **Rebuild:** the responses layer only (`schema`, `errors`, `request`, `continuity`,
  `translate`, `session`, `router`) rewritten from the spec text into a throwaway package;
  everything below it (`chat.stream`, models, config, auth) reused unchanged.
- **Oracle:** a differential harness runs old and new side by side with a **pinned upstream** —
  fixed `TurnPlan` (fixed message/conversation uuid), canned `ChatEvent` sequence, frozen
  `translate.time`, deterministic new-conversation uuid — so any byte difference is a genuine
  drift, not nondeterminism.
- **Corpus:** 25 scenarios covering every spec branch. 23 are byte-diffed; the two timing/config
  cases (`connection_limit_frame`, `_ws_user` anonymous) are asserted structurally.
- Rebuild and harness are discarded; this report is the deliverable.

## Result

```
23/23 byte-diffed scenarios  → identical
 2/2  structural scenarios   → identical
─────────────────────────────────────────
25/25 identical
```

Scenarios: string/array(multi-part) input · default-vs-pinned model · v4-pin override · cache hit ·
continuation by `previous_response_id` and by `conversation` · errors (unknown model, unknown
prev-id, empty input, conversation mismatch, conversation_not_found, no_answer) · SSE happy path ·
mid-stream `response.failed` · pre-stream HTTP-envelope error · WS happy path · `generate:false`
warm-up (silent + stale-conv frame) · WS error frames (invalid JSON, wrong type, validation,
error-while-generating) · connection-limit frame · anonymous auth.

## Gap log

Severity: **BLOCKER** = a blind spec-only build is wire-wrong here until it reads the code;
**INFER** = spec is silent but the obvious inference is correct (or the detail is wire-invisible);
**STYLE** = internal only.

### Wire-visible blockers — a blind build drifts on these

| # | Clause | Gap | What the code does |
|---|---|---|---|
| 1 | §5 (translate) | The spec documents the 9 **output** events exhaustively but **never names the upstream `ChatEvent` inputs** that trigger them. §5.1 lists only the *ignored* inputs (`step`/`intent`/`routing`/`agency_*`). You cannot write `consume()` at all without knowing the trigger names. | `answer` → the 6 output-item events; `done` → `response.completed`; `error` → `response.failed`. |
| 2 | §5 (router) | SSE/WS JSON serialization must use `ensure_ascii=False`. Only *derivable* from the spec printing raw Thai (`คำตอบเต็ม`) in its examples; never stated. A default `json.dumps` emits `\uXXXX` and every Thai-carrying frame diffs. | `json.dumps(event, ensure_ascii=False)` in both the SSE renderer and the WS `send`. |
| 3 | §1/§4 (request) | The response `model` **echoes the requested id verbatim** — for the default id the response `model` is `"thai-citizen-guide"`, not the resolved `"…-v5"`. §4's example only ever shows a *pinned* request, so a reader can plausibly emit the resolved version. | `resolve_model` returns the requested string unchanged. |
| 4 | §6 (translate) | `portal.agency_ids` source shape. §6 says only "gathered from every section's agencies" — not that the data is `answer.sections[].agencies[]["id"]` (upstream OneChat shape, undocumented here). | `[a["id"] for s in data["sections"] for a in s["agencies"]]`. |
| 5 | §2.1 (request) | The **error `message` strings** for input validation are not given (§2.1 states only `400`, `param:"input"`). A blind build invents different text → the `message` field diffs. | `"\`input\` must not be empty."` / `"The last item of \`input\` must be a message with role 'user'."` |
| 6 | §3 (continuity) | The **mismatch `message`** for `conversation` vs `previous_response_id` is not given (§3 states only `param:"conversation"`, `400`). | `"\`conversation\` does not match the conversation of \`previous_response_id\`; supply only one."` |
| 7 | §8 (router) | **Binary-frame rejection** — neither the behaviour nor the message is in §8's error table (which lists invalid-JSON / wrong-type / validation / generating faults, but not binary). | Sends an `invalid_request_error` "…accepts text frames only…" and keeps the socket open. |
| 8 | §4 (translate) | The **degrade case**: when the answer is empty, `output` must stay `[]` in the completed body. §4 shows only a *populated* `output`; the "empty until the answer arrives" line implies but does not state the `and self.answer` guard. | `if with_output and self.answer:` gates the `output` array. |

Inconsistency worth noting: the spec **does** pin some `message` strings verbatim (unknown model,
`previous_response_not_found`, the connection-limit frame, the WS invalid-JSON/wrong-type/generic
frames) but omits others (#5, #6, #7). Message text is either part of the contract or it isn't;
right now it's half-in.

### Inferable / wire-invisible

| Clause | Gap | Note |
|---|---|---|
| §5 (router) | Prelude validation **order** (model → input → continuity) on a multi-error request. | Wire-visible only when a request violates several at once; not in the corpus. |
| §3 (continuity) | `_same_conversation` compares as **UUID values** (case-insensitive), and the prev-id lookup filters `role="assistant"`. | Inferable; wire-visible only on case-variant ids / id collisions. |
| §4 (translate) | `item_id` = `"msg_" + response_id.removeprefix("resp_")`. | Shown by matching example uuids — inferable. |
| §1 (request) | Unknown `CHAT_STREAM_VERSION` falls back to `v5`. | Wire-invisible unless misconfigured. |
| §8 (session) | `generate:false` with no continuation ids is a silent no-op; `RecursionError` is also caught as invalid JSON. | Inferable / not in corpus. |
| §1/§6 (router) | A pinned model overrides `CHAT_STREAM_VERSION` by mutating the plan after `prepare_turn`. | Effect (portal.stream_version) is stated in §1; the mechanism is code. |
| §5 (router) | The generator is primed inside the handler so a prelude raise precedes `StreamingResponse`. | §5 states the *requirement*; the mechanism is wire-invisible. |
| §7 (errors) | `ResponsesApiError` constructor defaults and the code→status pairing. | Derivable from the §7 table. |
| §2 (schema) | `model` field needs `protected_namespaces=()` or pydantic warns. | Internal; no wire impact. |

## Recommendation

One change closes most of the gap between "documents the output" and "regenerates the code":

1. **Add an `input` section** documenting the OneChat `ChatEvent` vocabulary the translator
   consumes — at minimum the `answer` / `done` / `error` names and the `answer` payload shape
   (`answer`, `summary`, `references`, `sections[].agencies[].id`). This closes blockers #1 and #4,
   the only two a reader genuinely *cannot* infer.
2. **State the serialization rule** (`ensure_ascii=False`) once — closes #2.
3. **Pin the remaining `message` strings** (#5, #6) and **add the binary-frame row** to §8 (#7),
   for parity with the messages already pinned.
4. **State the two easily-missed rules** explicitly: response `model` echoes the request (#3), and
   `output` stays `[]` on an empty answer (#8).

With those, a blind spec-only rebuild would be byte-identical from the first run.
