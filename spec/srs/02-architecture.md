# SRS — 02: สถาปัตยกรรม

← [ดัชนี](README.md)

---

> เอกสารนี้สะท้อนสถานะโค้ดปัจจุบัน · ภาพรวมระดับสูงดู [01-overview.md](01-overview.md)

## Tech Stack

| Layer | เทคโนโลยี |
|---|---|
| Web framework | FastAPI + Uvicorn |
| Orchestration | LangGraph (`StateGraph`) — compile 4 กราฟ |
| Agency discovery | MCP runtime catalog (`fastmcp.Client`) ต่อ request |
| Async HTTP | httpx |
| LLM gateway | `MultiplexedLLMClient` — vLLM หรือ OpenRouter (OpenAI-compatible), main+fallback, config มาจาก Postgres runtime |
| LLM config/cost storage | Postgres (asyncpg) — `llm_provider_config` (pgcrypto-encrypted key), `llm_call_log` |
| Config | Pydantic Settings + `.env` |
| Reliability | tenacity (retry) + `CircuitBreakerManager` + `asyncio.wait_for` |
| Logging | structlog + `request_id` middleware |
| Session history | Redis (optional) |
| Testing | pytest + pytest-asyncio + httpx |
| Containerization | Docker + Compose + Caddy |

## โครงสร้างชั้น (Layers)

| ชั้น | ตำแหน่ง | หน้าที่ |
|---|---|---|
| API | `app/api/` | FastAPI router, dependency injection |
| Orchestrator | `app/graph/orchestrator.py` | สร้าง/รัน LangGraph `StateGraph` |
| Nodes | `app/graph/nodes/` | ฟังก์ชัน async หนึ่งไฟล์ต่อหนึ่ง node |
| State | `app/graph/state.py` | `OrchestratorState` TypedDict, `OrchestratorDependencies` |
| Adapters | `app/adapters/` | `AgencyAdapter` ABC + `GenericAdapter` + `MockAgencyAdapter` |
| Services | `app/services/` | MCP discovery, session history store, `llm_config_store.py`/`llm_cost_log_store.py` (Postgres) |
| LLM | `app/llm/` | `protocol.py` (`SynthesisLLM`), `multiplexed.py` (`MultiplexedLLMClient`), `openai_compatible.py`, `pricing.py`, `prompts.py` |
| Models | `app/models/` | Pydantic schema: request, response, agency, stream |
| Utils | `app/utils/` | circuit breaker, logging, error handlers, stream queue |
| Config | `app/core/settings.py`, `app/core/db.py` | Pydantic Settings (LRU-cached); asyncpg pool lifecycle (created/closed in `app/main.py`'s `lifespan`) |

## LangGraph Flow

ทั้ง 5 endpoint ใช้ node ชุดเดียวกัน ต่างกันแค่ format node ปลายทาง:

```
START
  ▼
validate_request          ดึง query จาก request เข้า state
  ▼
resolve_runtime_agencies  discover หน่วยงานจาก mcp_endpoint_url
  ▼
analyze_query             LLM call เดียว: classify intent + decompose + route
  │
  ├─ intent=chitchat     ─► respond_chitchat   ─┐
  ├─ intent=capability   ─► respond_capability  ┤
  ├─ intent=out_of_scope ─► respond_refusal     ┤
  │                                             ▼
  └─ intent=search ─► invoke_agencies ─► verify_relevance ─► [v5: summarize_answer] ─► [format node]
                      (ขนาน + retry +      (LLM ให้คะแนน       (บทสรุปภาพรวม
                       circuit breaker)     ต่อคำตอบ,           + citation, 1 LLM
                                            fail-closed=0.0)    call ต่อ request)   ▼
                                                                                  END
```

format node ต่างกันตามกราฟ:

| กราฟ | format node | ที่อยู่ |
|---|---|---|
| v1 | `synthesize_answer` → `format_response` | `nodes/synthesize.py`, `nodes/format.py` |
| v2 | `_format_raw_response` | inline ใน `orchestrator.py` |
| v3 / v4 | `format_v3_response` | `nodes/format_v3.py` (ใช้ `section_builder.py` ร่วมกับ v5) |
| v5 | `summarize_answer` → `format_v5_response` | `nodes/summarize.py`, `nodes/format_v5.py` |

> `respond_chitchat` (`_respond_chitchat`) และ `_format_raw_response` เป็นฟังก์ชัน inline ใน `orchestrator.py` ไม่ใช่ไฟล์แยก — node อื่นทั้งหมดอยู่ใน `app/graph/nodes/`

## 4 กราฟ, 5 endpoint

`ChatOrchestrator.__init__` compile กราฟ 4 ตัว v4 ใช้กราฟตัวเดียวกับ v3 แต่รันคนละวิธี:

| Endpoint | เมธอด | กราฟ | วิธีรัน |
|---|---|---|---|
| `POST /v1/chat` | `run()` | `_graph` | `ainvoke` — รอผลก้อนเดียว |
| `POST /v2/chat` | `run_raw()` | `_raw_graph` | `ainvoke` |
| `POST /v3/chat` | `run_v3()` | `_v3_graph` | `ainvoke` |
| `POST /v4/chat` | `run_stream(endpoint="v4")` | `_v3_graph` | `astream` — stream event ระหว่างทาง |
| `POST /v5/chat` | `run_stream(endpoint="v5")` | `_v5_graph` | `astream` — เหมือน v4 + `summarize_answer` (บทสรุป+citation บนสุด) |

## Node แต่ละตัว

| Node | ไฟล์ | หน้าที่ | เรียก LLM |
|---|---|---|---|
| `validate_request` | `validate.py` | คัด `query` จาก request เข้า state | — |
| `resolve_runtime_agencies` | `resolve_runtime_agencies.py` | discover หน่วยงานจาก MCP; ล้มเหลว → คืน list ว่าง + error | — |
| `analyze_query` | `analyze_query.py` | classify intent, แตก sub-question, จัด routing; LLM fail → raise (ไม่ degrade เงียบ ๆ) | ✅ 1 ครั้ง |
| `respond_chitchat` | `orchestrator.py` (inline) | ตอบ chitchat ตรงจากผล analyze_query (มาตรฐาน: ลงท้าย "ครับ", ไม่มี emoji, ประโยคเดียวกันเสมอ) | — |
| `respond_capability` | `respond_capability.py` | สร้างคำตอบรายชื่อหน่วยงานที่ให้บริการ — สร้างจาก `data_scope` ตรง ๆ ในโค้ด ไม่เรียก LLM | — |
| `respond_refusal` | `orchestrator.py` (inline) | ตอบ refusal จาก LLM (fallback คงที่, มาตรฐานเดียวกับ chitchat) เมื่อ intent=out_of_scope (รวม prompt injection/jailbreak) | — |
| `invoke_agencies` | `invoke.py` | ยิง HTTP ทุกหน่วยงานแบบขนาน | — |
| `verify_relevance` | `verify.py` | ให้คะแนนความเกี่ยวข้องต่อคำตอบ; `score > 0.5` = ผ่าน; LLM fail → fallback `0.0` (fail-closed) | ✅ N ครั้ง |
| `summarize_answer` | `summarize.py` | เขียนบทสรุปภาพรวมพร้อม `[n]` citation จาก agency ที่ผ่าน verify ทั้ง request (v5 เท่านั้น); LLM fail → degrade เงียบ ๆ เป็น v4-identical | ✅ 0–1 ครั้งต่อ request |
| `synthesize_answer` | `synthesize.py` | เรียบเรียงคำตอบ Markdown (v1 เท่านั้น); LLM fail → raise | ✅ 1 ครั้ง |
| `format_response` | `format.py` | map state → `ChatData` (v1) | — |
| `format_v3_response` | `format_v3.py` | จัด section + debug → `ChatV3Data` (v3/v4) ผ่าน `section_builder.build_sections()` | — |
| `format_v5_response` | `format_v5.py` | ต่อบทสรุปจาก `summarize_answer` เข้ากับ section เดียวกับ v4 (`build_sections()` เดิม) → `ChatV5Data` (v5 เท่านั้น) | — |

`section_builder.py`'s `build_sections()` เป็น helper กลาง (ไม่ใช่ node) ที่ `format_v3_response` และ `format_v5_response` เรียกร่วมกัน — รับประกันว่าเนื้อหา `sections[]` ของทั้งสองเวอร์ชันตรงกันทุกตัวอักษร ไม่มี citation/trim ปนอยู่เลย

LLM helper `build_debug_info` (`debug_utils.py`) สร้าง `DebugInfo` struct ให้ v3/v4/v5 — ไม่ใช่ node

**จำนวน LLM call ต่อ request:** v1 = `2 + N` (analyze + verify×N + synthesize), v2/v3/v4 = `1 + N` (analyze + verify×N), v5 = `1 + N` (analyze + verify×N) + 0–1 (summarize_answer, ครั้งเดียวไม่ว่าจะมี agency กี่ราย) โดย N = จำนวนคำตอบหน่วยงานที่ไม่ error — v5 ปัจจุบันเรียก LLM **น้อยกว่า**ดีไซน์เดิม (เดิมมี trim×N + connect×M เพิ่ม)

## v4/v5 — SSE Streaming

v4 รัน `_v3_graph`, v5 รัน `_v5_graph` ด้วย `astream(stream_mode="updates")` แล้วแปลง state update ของแต่ละ node เป็น SSE event นอกจากนี้ `invoke_agencies` ยัง push event `agency_start`/`agency_responded` แบบ live ผ่าน side-channel queue (`app/utils/stream_context.py`) เพื่อให้ client เห็นความคืบหน้าระหว่างที่หน่วยงานทยอยตอบ — ไม่ต้องรอ node จบ ถ้า node ไหน raise exception ที่ไม่ได้ถูกจับไว้ `run_stream()` จะ catch ไว้ ปิดทุก step ที่ค้างเป็นสถานะ `error` แล้วส่ง fallback answer แทนการปล่อยให้ stream ตายกลางทาง

รายละเอียด event ทั้งหมดดู [../api/v4.md](../api/v4.md) และ [../api/v5.md](../api/v5.md)

## OrchestratorState

state ทั้งหมดไหลผ่าน `OrchestratorState` (TypedDict, `total=False`) ใน `app/graph/state.py` — สร้างใหม่ทุก request ไม่มีการ persist key หลัก: `query`, `runtime_agencies`, `intent`, `selected_agencies`, `agency_queries`, `agency_results`, `section_for_query`, `routing_debug`, `formatted_*_data`, และ `timing_*_ms`

## การตัดสินใจเชิงออกแบบ

**MCP-first สำหรับหน่วยงาน ไม่มี database ของหน่วยงาน.** หน่วยงานถูก discover ตอน request จาก `mcp_endpoint_url` ที่ client ส่งมา `MCPCatalogDiscovery` ใช้ `fastmcp.Client` เรียก tool `list_agency` (Postgres ที่มีอยู่ใช้เก็บแค่ LLM provider config + cost log เท่านั้น — ดู "LLM Provider System" ด้านล่าง)

**Decompose + route ด้วย LLM call เดียว.** `analyze_query` ทำ classify + แตกคำถาม + จัด agency + ตั้ง section label ใน CoT call เดียว ต่อ sub-question: confidence ≥ 0.9 → ส่งเฉพาะ agency ที่ match; < 0.9 → broadcast ทุกหน่วยงาน LLM fail ตรงนี้ → raise ตรง ๆ ไม่ degrade ไปเป็น default ที่ดูเหมือนใช้งานได้

**LLM Provider System (main/fallback, runtime-configurable).** `MultiplexedLLMClient` (`app/llm/multiplexed.py`) implement `SynthesisLLM` protocol เดียวกับที่ node ทุกตัวเรียก แต่ละ call โหลด config `main`/`fallback` ปัจจุบันจาก Postgres (TTL cache สั้น ๆ ในโปรเซส) ลอง `main` ผ่าน `OpenAICompatibleClient` (รองรับทั้ง vLLM และ OpenRouter ด้วย request/response shape เดียวกัน) ถ้าล้มเหลวลอง `fallback` แล้ว log ทุกครั้งที่เรียก (สำเร็จ/ล้มเหลว, token, cost) ลง `llm_call_log` ไม่มี `main` ตั้งไว้เลย → raise `NoLlmProviderConfiguredError` ตั้งค่าผ่านหน้า LLM Setting ของ debug console (`/v1/llm-settings`) ไม่ใช่ env var

**Reliability stack ต่อหน่วยงาน.** ใน `_invoke_single_agency`: `circuit_breaker.allow()` → `AsyncRetrying` (tenacity, exponential jitter) → `asyncio.wait_for` timeout การเรียกทั้งหมดขนานด้วย `asyncio.as_completed` หน่วยงานล่มถูกบันทึกเป็น `AgencyResult.error` ไม่ทำให้กราฟ crash

> **retry เฉพาะ `RuntimeError`** — timeout ไม่ถูก retry เพราะหน่วยงานเป็น LLM agent ที่ช้าโดยธรรมชาติ การ retry timeout แค่เผาเวลาอีกหนึ่งรอบ timeout

**Stateless + session แยก.** ไม่มี state ข้าม request ใน process ประวัติการสนทนาเก็บใน Redis ผ่าน `HistoryStore` ที่ inject เป็น FastAPI dependency

## Session History

| ประเด็น | ค่า |
|---|---|
| เปิดใช้เมื่อ | ตั้ง `REDIS_URL` |
| ไม่มี Redis | `NullHistoryStore` (no-op) — ระบบยังทำงานได้ |
| เก็บสูงสุด | 5 turns (10 messages) ต่อ session |
| TTL | `SESSION_TTL_SECONDS` (ค่าเริ่มต้น 1800 วินาที) |
| Truncate | คำตอบ assistant ตัดที่ 800 ตัวอักษรก่อนเก็บ |
| Key | `onechat:session:{session_id}` |

ทุก endpoint โหลด history ก่อนรันกราฟ และ `v1/v2/v3` บันทึกกลับหลังตอบ

**session_id ส่งต่อให้ agency ปลายทาง:** `session_id` ที่ endpoint รับมา (หรือสร้างใหม่ถ้า frontend ไม่ส่ง) ถูก propagate ผ่าน `OrchestratorState["session_id"]` ไปจนถึง `GenericAdapter.call(query, session_id=...)` ถ้า agency declare field ชื่อ `session_id` / `conversation_id` / `thread_id` ใน `expected_payload` ของ MCP (เก็บใน `AgencyConfig.request_session_field`) adapter จะใส่ session_id ลงไปให้ — ทำให้ agency ที่รองรับ session memory map turn ของผู้ใช้กับ session ฝั่งตัวเองได้ ดู [04-agents.md](04-agents.md)

## Non-Functional Requirements

| ด้าน | ข้อกำหนด |
|---|---|
| Performance | เรียก agency ขนานเสมอ; รองรับ request พร้อมกัน |
| Reliability | timeout + retry + circuit breaker ต่อ agency; MCP/LLM ล้มเหลวมี fallback |
| Security | secret ผ่าน env เท่านั้น; SSRF guard บล็อก IP วงใน (ดูหมายเหตุด้านล่าง) |
| Observability | `request_id` ทุก request, header `X-Response-Time-MS`, per-step timing ใน debug |
| Deployment | stateless, container-based, scale horizontal ได้ |

> **หมายเหตุ SSRF:** `_validate_ssrf_url` ใน `app/models/agency.py` บล็อก IP แบบ private/loopback/link-local/reserved และ hostname ต้องห้าม แต่ **ไม่ได้บังคับ HTTPS** — `http://` ที่ชี้ public IP ผ่านได้ ดู [06-bugs.md](06-bugs.md)

## เอกสารที่เกี่ยวข้อง

- [03-api.md](03-api.md) / [../api/](../api/) — endpoint และ schema ทั้ง 5 เวอร์ชัน
- [04-agents.md](04-agents.md) — งาน LLM และ agency adapter
- [06-bugs.md](06-bugs.md) · [05-roadmap.md](05-roadmap.md)
