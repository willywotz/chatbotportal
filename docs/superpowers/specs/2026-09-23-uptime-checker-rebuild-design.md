# Uptime Checker Rebuild — Design

Date: 2026-09-23
Branch: `feat/uptime-checker-rebuild`
Status: Draft for review

## 1. Purpose

Rebuild the agency uptime checker. Today one APScheduler job
(`agency_chat_test`) probes every agency each interval, writes a
`ConnectionLog` row per probe, then reconciles agency status. The whole
scheduler starts inside the FastAPI lifespan, and production runs
`uvicorn --workers 4`, so every worker runs its own copy. The result is
four times the probe traffic, four times the log rows, and an unsafe
event outbox.

This rebuild has three goals:

1. **Scalability / reliability** — one probe per agency per interval,
   spread safely across the four workers, with retries and jitter.
2. **Event-driven decoupling** — incident transitions become domain
   events; a consumer projects them to the audit trail. Alert delivery
   can subscribe later with no rework.
3. **Better data model / history** — per-agency check state, downsampled
   uptime buckets for cheap 24h/7d/30d reads, and first-class incidents.

The probe behaviour itself does not change: one reachability probe per
connection type (HEAD then GET), any HTTP response counts as reachable,
only a transport failure is an error.

## 2. Scope

### In scope
- New `monitoring` feature: models, repositories, services.
- Claim-based (sharded) scheduling with `FOR UPDATE SKIP LOCKED`.
- Retries with exponential backoff and jitter; per-agency intervals.
- Synchronous write of check-state, uptime bucket, and incident.
- Incident domain events plus an in-process audit consumer.
- Public read path switches to buckets; add `uptime_7d_pct` and
  `uptime_30d_pct` while keeping `uptime_24h_pct`.
- Targeted fix to the event outbox read (`FOR UPDATE SKIP LOCKED`) so the
  four workers do not double-deliver events.
- Retire the old `agency_chat_test` and `reconcile_statuses` jobs and the
  `ConnectionLog` uptime write.

### Out of scope (deferred, flag as follow-up)
- External alert delivery (email/webhook). Incidents are recorded and
  emitted as events only.
- **No history backfill.** History starts at cut-over. Windows fill over
  time; an agency with no buckets yet reads `null` uptime.
- The other per-worker duplicated scheduler jobs (brief regen, popular
  questions, eval, purge). The outbox fix makes `dispatch_pending` safe;
  the rest keep their current behaviour and get a follow-up note.

## 3. Architecture

### Feature placement (feature-based clean architecture)
New feature `backend/app/features/monitoring/`:

```
features/monitoring/
  models/       check_state.py, uptime_bucket.py, incident.py
  repositories/ check_state.py, uptime_bucket.py, incident.py
  services/     monitor.py      # tick -> claim -> probe -> record
                incidents.py    # incident state machine + event publish
                uptime_read.py  # window aggregation for the read path
```

- The probe `test_connection` stays in `features/agency/services/agency.py`
  (it is also used by the manual test endpoint). Monitoring imports it;
  no churn to the probe.
- New models are registered in `app/core/registry.py` so
  `Base.metadata` and Alembic autogenerate see them.
- Dependency rule holds: `monitoring` depends on `core` (events, db,
  base, utils) and imports the `agency` probe function only. No
  feature-router to feature-router calls.

### Data flow
```
monitor_tick (every MONITOR_TICK_SECONDS, in each worker)
  -> claim due agencies (FOR UPDATE SKIP LOCKED, lease + bump next_check_at)
  -> probe each (bounded concurrency, retries + backoff + jitter)
  -> record result (one transaction per agency):
       update agency_check_state
       upsert current hourly uptime_bucket
       open/close incident on transition
       publish agency.incident_opened / agency.incident_closed
  -> outbox dispatch_pending delivers incident events
       -> _on_incident_opened / _on_incident_closed -> audit_logs
public_status (read)
  -> aggregate uptime_bucket over 24h / 7d / 30d
```

## 4. Data model

Three new tables. Conventions from MEMORY.md: `timestamptz` everywhere,
`Enum(..., native_enum=False, create_constraint=False, length=n)` for
enum columns, `Base` naming convention, FK `ondelete="CASCADE"`.

### `agency_check_state` — one row per agency
Source of truth for scheduling and current health.

| column | type | notes |
|---|---|---|
| `agency_id` | UUID PK, FK→agencies cascade | one row per agency |
| `enabled` | bool | false for draft/disabled; skipped by the claim |
| `interval_seconds` | int | per-agency interval; default `DEFAULT_CHECK_INTERVAL_SECONDS` |
| `next_check_at` | timestamptz, **indexed** | the claim key |
| `leased_until` | timestamptz null | lease while a probe is in flight; expiry allows reclaim after a worker crash |
| `last_checked_at` | timestamptz null | |
| `last_status` | enum `up`/`down`/`unknown` | |
| `last_latency_ms` | int | |
| `consecutive_failures` | int, default 0 | drives the incident threshold |
| `current_incident_id` | UUID null, FK→incident | set while down |

Index: btree on `next_check_at` (partial `WHERE enabled` is optional).

### `uptime_bucket` — hourly downsample
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `agency_id` | UUID FK→agencies cascade | |
| `bucket_start` | timestamptz | truncated to the hour |
| `total_checks` | int | |
| `ok_checks` | int | |

Unique constraint `(agency_id, bucket_start)` — the upsert conflict
target. Windows are computed by summing rows since a cutoff. Hourly only
(daily is a later optimisation). Retention
`UPTIME_BUCKET_RETENTION_DAYS`, longer than the raw `ConnectionLog`
retention, so history survives the log purge.

### `incident` — up→down / down→up episodes
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `agency_id` | UUID FK→agencies cascade | |
| `started_at` | timestamptz | |
| `ended_at` | timestamptz null | null = ongoing |
| `detail` | text | last error at open |

Partial unique index `(agency_id) WHERE ended_at IS NULL` — at most one
open incident per agency.

### `ConnectionLog` — unchanged schema
Stop writing `action="test"` rows. It keeps only `action="query"` logs.
The old `connection_uptime_by_agency` read is removed.

## 5. Scheduling — claim-based sharding

One job `monitor_tick` runs every `MONITOR_TICK_SECONDS` (e.g. 15s) in
every worker. Safe because workers claim disjoint work.

**Claim (one short transaction), in `repositories/check_state.py`:**
```
SELECT * FROM agency_check_state
WHERE enabled AND next_check_at <= now()
ORDER BY next_check_at
FOR UPDATE SKIP LOCKED
LIMIT :MONITOR_CLAIM_BATCH
```
In the same transaction, for each claimed row set
`leased_until = now() + MONITOR_LEASE_SECONDS` and
`next_check_at = now() + interval_seconds + jitter`, then commit. Two
workers never grab the same agency (`SKIP LOCKED`); the `next_check_at`
bump prevents re-claim within the tick; the lease lets a crashed worker's
row be reclaimed after expiry. Jitter spreads load across ticks.

**Probe** each claimed agency under a semaphore
(`MONITOR_PROBE_CONCURRENCY`). A check is `up` if any attempt is
reachable; **retry** up to `CHECK_RETRY_MAX` with exponential backoff
(`CHECK_BACKOFF_BASE_MS`) plus jitter (`CHECK_JITTER_MS`) before
concluding `down`. Each attempt still honours `CONNECTION_TEST_TIMEOUT`.

The scheduler opens its own `AsyncSessionLocal()` + `begin()` per unit of
work (per MEMORY.md: non-request contexts own their session; services
never commit).

## 6. Write path — synchronous, one transaction per agency

Per result, in its own transaction (so one failure never blocks the
batch):

1. Update `agency_check_state`: `last_checked_at`, `last_status`,
   `last_latency_ms`; `consecutive_failures = 0` on success else `+1`;
   clear `leased_until`.
2. Upsert the current hourly `uptime_bucket`
   (`INSERT ... ON CONFLICT (agency_id, bucket_start) DO UPDATE`):
   `total_checks + 1`, and `ok_checks + 1` when up.
3. Incident state machine (`services/incidents.py`):
   - `consecutive_failures >= FAILURE_THRESHOLD` and no open incident →
     insert incident, set `current_incident_id`,
     `publish(session, "agency.incident_opened", {...})`.
   - success and an open incident → set `ended_at = now()`, clear
     `current_incident_id`, `publish(session, "agency.incident_closed", {...})`.
4. Preserve the **maintenance auto-recover**: a successful probe on a
   `maintenance` + `auto_maintenance` agency recovers it to `active`
   (behaviour moved from `run_connection_test`). The old
   `reconcile_statuses` job is retired; its status logic folds into this
   state machine.

`publish` appends to the existing outbox inside the same transaction, so
the incident row and its event commit atomically.

### Consumer
`event_consumers.py` gains `_on_incident_opened` and `_on_incident_closed`,
each projecting to `audit_logs` via `audit_repo.create` (mirrors the
existing `agency.status_changed → audit` consumer), registered in
`register_consumers()`. Deferred alert delivery subscribes to the same
two event types later.

### Outbox fix (targeted)
`app/core/repositories/event.py::pending` adds
`.with_for_update(skip_locked=True)` so concurrent `dispatch_pending`
runs across the four workers do not read and handle the same rows.
Without this, incident events (and today's `status_changed` events)
double-deliver.

### Manual test endpoint
`run_connection_test` (manual, on-demand) routes through the same record
path, so a manual test also updates state, bucket, and incident.

## 7. Read path — public status

`services/uptime_read.py`:
`uptime_by_agency(session, since) -> dict[agency_id, (total, ok)]`,
summing `uptime_bucket` rows with `bucket_start >= since`, grouped by
agency (one query for all agencies).

`analytics/services/public_status.py` computes three windows (24h, 7d,
30d) and keeps the contract:
```json
{
  "name": "...",
  "status": "active",
  "uptime_24h_pct": 99.5,   // kept
  "uptime_7d_pct": 99.1,    // added
  "uptime_30d_pct": 98.7,   // added
  "incident_open": false    // added
}
```
`uptime = round(ok / total * 100, 1) if total else None` — an agency with
no buckets in a window reads `null`.

## 8. Configuration (15-Factor III — all from env via `settings`)

New settings:
`MONITOR_TICK_SECONDS`, `MONITOR_CLAIM_BATCH`, `MONITOR_LEASE_SECONDS`,
`MONITOR_PROBE_CONCURRENCY`, `DEFAULT_CHECK_INTERVAL_SECONDS`,
`CHECK_RETRY_MAX`, `CHECK_BACKOFF_BASE_MS`, `CHECK_JITTER_MS`,
`FAILURE_THRESHOLD`, `UPTIME_BUCKET_RETENTION_DAYS`.

Retire `HEALTH_CHECK_INTERVAL_MINUTES`. Keep `CONNECTION_TEST_TIMEOUT`.
`AGENCY_CHAT_CONCURRENCY` / `AGENCY_CHAT_TIMEOUT` are replaced by the
`MONITOR_*` equivalents. OTel spans carry onto the tick and each probe.

## 9. Error handling

- One transaction per agency result — a single failure does not block the
  batch.
- A probe exception is a recorded `down`, not a crash.
- A worker that crashes mid-probe: `leased_until` expiry lets another
  worker reclaim the agency on a later tick.
- Events are at-most-once (outbox has no retry). Acceptable for the audit
  projection; note idempotency only if a future consumer needs it.

## 10. Migration & rollout

Alembic revision (autogenerate, then review per MEMORY.md):
1. Create `agency_check_state`, `uptime_bucket`, `incident` with indexes
   (the `next_check_at` btree, the bucket unique key, the partial-unique
   open-incident index).
2. Seed one `agency_check_state` row per existing agency
   (`enabled` from status, `next_check_at = now()`,
   `interval_seconds = DEFAULT_CHECK_INTERVAL_SECONDS`).
3. Add the outbox `skip_locked` change (code only, no schema).

Cut-over (code): remove `agency_chat_test`, `_run_agency_item`, and the
`reconcile_statuses` job from `scheduler.py`; add the `monitor_tick`
job; stop writing `test` rows to `ConnectionLog`; point `public_status`
at buckets. **No history backfill** — history starts now.

`init_db()` runs `alembic upgrade head` at startup under the existing
advisory lock, so the new tables appear before the first tick.

## 11. Testing (TDD — red → green → refactor, mandatory)

- **Claim:** two concurrent claims never take the same agency
  (`SKIP LOCKED`); the `next_check_at` bump blocks re-claim in a tick; an
  expired lease is reclaimable.
- **Retry/backoff:** up on attempt N counts up; all attempts failing
  counts down (probe mocked).
- **Bucket:** upsert increments `total`/`ok`; window aggregation sums
  correctly across hour boundaries.
- **Incident machine:** opens on threshold, closes on recovery, one-open
  invariant, correct events published.
- **Maintenance auto-recover** preserved.
- **Consumer:** incident events project to `audit_logs`.
- **Outbox:** `skip_locked` prevents double-delivery under concurrent
  dispatch.
- **Read/API:** `public_status` returns the three windows plus status;
  `uptime_24h_pct` contract preserved; empty windows read `null`.
- **Integration:** one full `monitor_tick` over seeded agencies.

## 12. Open questions / follow-ups

- Alert delivery (email/webhook) as a later consumer of the incident
  events.
- Daily uptime buckets if 30d hourly sums become costly.
- De-duplicating the other per-worker scheduler jobs (brief, popular,
  eval, purge).
