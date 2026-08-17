# Methodology Compliance Report — 2026-08-17

This report scores the code against three rules. It gives evidence and next steps.
It does not change code. Written in Simplified Technical English.

Scope: `backend/` (Python FastAPI), `agent-proxy/` (Go), `mcp-server/` (Go), `frontend/` (React).

Score key: **Good** = the rule holds. **Partial** = the rule holds in some places only.
**Gap** = the rule does not hold.

---

## 1. Clean Architecture — Partial

Clean Architecture needs one rule: inner layers must not depend on outer layers.
Routers (interface layer) must call services (use-case layer). Services must own the
data model (entity layer). Routers must not touch the database directly.

### Evidence
- A service layer exists: `backend/app/services/` has 20+ modules (`user.py`, `agency.py`,
  `audit.py`, and more).
- Write paths follow the rule. Example: `create_user` calls the service, not the ORM.
  See `backend/app/routers/users.py:60` (`user_service.create_user(body)`).
- Read paths break the rule. The same file builds an ORM query in the router.
  See `backend/app/routers/users.py:39-53` (`User.filter(...)`, `qs.order_by(...)`).
- All 26 routers import `app.models` directly (ORM entities). The interface layer depends
  on the persistence layer.

### Problem
The pattern is not consistent. Writes go through services. Reads bypass them. This mixes
two layers in one file. Business rules for queries live in the router, not the use-case layer.

### Recommendation (small steps)
1. Move each router's query logic into its service. Example: add `user_service.list_users(...)`.
2. Return schema objects from services, not ORM rows, so routers stop importing `app.models`.
3. Do one router per commit. Keep the tests green after each commit.

---

## 2. 15-Factor App — Partial (mostly Good)

### Good
- **Factor III (Config):** Config comes from environment variables.
  `backend/app/config.py` uses `pydantic-settings` `BaseSettings` and reports overrides.
- **Factor IV (Backing services):** The database and Redis attach by URL
  (`DATABASE_URL`, `REDIS_URL`). The code can swap them without a code change.
- **Factor V (Build, release, run):** Dockerfiles and `compose.yaml` separate the stages.

### Gaps
- **Factor VI (Stateless / disposability):** Agency logos write to local disk.
  `UPLOAD_DIR = "/app/uploads"` (`backend/app/config.py`) is a named Docker volume.
  Local disk is not a shared backing service. Two backend replicas do not share it.
  Move uploads to object storage (S3-compatible) for horizontal scale.
- **Factor XI (Logs):** No central log config is present. A search for `basicConfig`,
  `dictConfig`, `FileHandler`, or `StreamHandler` in `backend/app` returns nothing.
  The app relies on the default handler. Set explicit structured logs to `stdout`.
- **Factor XII (Admin processes):** One-off admin tasks are HTTP routes, not one-off
  processes. See `backend/app/routers/seed.py` (`/seed/admin`, `/seed/agencies`, `/seed/all`).
  Move seed logic to a CLI or a management script that runs the same code.

---

## 3. Event-Driven Architecture — Gap (largest gap)

EDA needs components to talk through events, not only through direct calls. It needs a
producer, a channel (bus, queue, or log), and a consumer.

### Evidence
- No event bus, message queue, or pub/sub is present. A search for `publish`, `subscribe`,
  `emit`, `event_bus`, `celery`, `kafka`, `rabbitmq`, or an outbox returns nothing in
  `backend/app`, `agent-proxy`, or `mcp-server`.
- The only `dispatch` is Starlette middleware (`backend/app/middleware/session_refresh.py:15`).
  This is HTTP middleware, not a domain event.
- The nearest seam to an event is the audit trail. `record_audit(...)`
  (`backend/app/services/audit.py:10`) writes a row synchronously inside the request.

### Problem
The system is a synchronous request and response CRUD app. It is not event-driven today.

### Recommendation (careful, not speculative)
Do not add a broker before there is a need. That is over-engineering. Start small:
1. Turn `record_audit` into a domain-event write with the **outbox pattern**: the request
   writes the event row in the same database transaction as the state change.
2. Add one background reader that publishes outbox rows to a channel.
3. Add the first real consumer only when a second component needs the event.

This path gives true EDA in steps. Each step ships value on its own.

---

## Priority order

1. **Clean Architecture** (Partial → Good). Lowest risk. Clear, testable, one router per commit.
2. **15-Factor** logs + uploads + seed (Partial → Good). Medium risk. Touches config and infra.
3. **EDA** via the audit outbox (Gap → Partial). Highest effort. Do only when a consumer needs it.

## Already done (2026-08-17)
- Rule "full english route name": renamed `POST /auth/anon` to `POST /auth/anonymous`.
  Branch `refactor/full-english-route-names`. Tests pass.
