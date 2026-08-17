# Handoff — Consolidate Go services into the Python backend (2026-08-17)

Written in Simplified Technical English. This is the state at end of session.

## Goal
"Rewrite `agent-proxy` and `mcp-server` to the backend, target a single backend
language." Sequence requested: brainstorm → spec → user review → plan → implement
with agents. Result: one backend language (Python) and one backend service.

## Git state
- Work merged to `main` as merge commit `18dd7ee` (`git merge --no-ff`).
- Source branch: `refactor/consolidate-go-services-into-backend` (12 commits) — now deleted.
- **`main` is NOT pushed** — the merge is local only. `main` is ahead of `origin/main`.
- Working tree is clean.

## What was done

### agent-proxy → Python (new work)
The Go `agent-proxy` streaming reverse proxy is now Python, in the Clean Architecture layers:
- `app/services/agent_proxy.py` — `proxy(*, agency_id, method, headers, body, transport=None)`.
  It checks the id is a UUID (else 400), loads the agency (else 404), clones the request headers,
  removes `X-Forwarded*` and `Host`/`content-length`/`connection`/`transfer-encoding`, sets the
  agency `api_headers`, injects the W3C trace context, and forwards the body to the agency
  `endpoint_url` with an `httpx.AsyncClient` at `AGENCY_CHAT_TIMEOUT` (180 s). It streams the
  answer back with the upstream status and headers. After the stream it counts the call
  (`increment_calls`, 2xx only) and always writes one `ConnectionLog` row (`action="proxy"`,
  `connection_type="API"`, bounded bodies). Upstream error/timeout → 502 + error log.
- `app/routers/agent_proxy.py` — thin route `ALL /api/v1/agent-proxy/{agency_id}` that returns a
  `StreamingResponse` (hop-by-hop response headers removed).
- Registered in `app/main.py` under `/api/v1`.

### mcp-server → deleted (already existed in Python)
The Python backend already served an equivalent MCP at `/mcp` (`app/mcp/server.py`). The Go
`mcp-server` was a duplicate port. It is removed. `/mcp-v2` is dropped; `/mcp` stays.

### Route + auth wiring
- Callback path: `app/mcp/server.py` `_agent_proxy_endpoint` now builds
  `/api/v1/agent-proxy/{id}` (was `/agent-proxy/{id}`). nginx already sends `/api/*` to the
  backend, so no new nginx rule is needed.
- Auth: the proxy is an external OneChat callback with no portal API key. `app/auth/
  dependencies.py` adds an anchored single-segment bypass `^/api/v1/agent-proxy/[^/]+$` that
  skips ONLY the role allowlist. `tests/test_surface_parity.py` now enumerates the new route
  from the live route table.

### Go removal
- Deleted `agent-proxy/` and `mcp-server/`.
- `docker-compose.yaml`: removed both service blocks, their four Go build/module volumes, and
  their `depends_on` entries. `docker compose config` is valid.
- `nginx/routes.conf`: removed `location /agent-proxy/` and `location ^~ /mcp-v2` and the
  matching comment lines. The `/api` catch-all and `/mcp` route stay.

### Final-review parity fixes
A whole-branch review (Opus) found four cross-file parity issues the per-task reviews could not
see. All fixed with tests:
1. Trace continuation: `?traceparent` query fallback only wrapped the `/mcp` mount, not the main
   app. `app/main.py` now also exposes `asgi_app = QueryTraceparentASGI(app)` and
   `backend/Dockerfile` serves `app.main:asgi_app`, so query→header promotion runs before OTel
   extraction on every main-app route.
2. `total_calls` was a non-atomic read-modify-write (lost-update race). `increment_calls` now
   uses an atomic `F("total_calls") + 1` then refreshes.
3. The incoming `Host` header was forwarded to the agency. Now stripped.
4. Connection-log `latency_ms` now measures time-to-headers (as the Go proxy did), not
   time-to-last-byte.

## Verification
- Full backend suite on `main`: **852 pass / 6 skip** (`cd backend && .venv/bin/python -m pytest -q`).
- Both Go directories are gone; `grep -rnE 'mcp-v2|/agent-proxy/' backend/app nginx docker-compose.yaml`
  (excluding `/api/v1/agent-proxy`) is clean.
- The jaeger trace-export warnings in test output are unrelated (no OTel sidecar in test env).

## Process artifacts
- Spec: `docs/superpowers/specs/2026-08-17-agent-proxy-mcp-backend-consolidation-design.md`
- Plan: `docs/superpowers/plans/2026-08-17-agent-proxy-mcp-backend-consolidation.md`
- Method: subagent-driven development — a fresh builder per task and a fresh verifier per task
  (Build↔Verify), then the Opus whole-branch review with one fix wave. `CONTEXT.md` updated and
  committed by the orchestrator after each task.

## Open items / next steps
1. **Push `main`** if you want it on the remote (not done this session).
2. **Docker rebuild** before deploy: the backend entrypoint changed to `app.main:asgi_app`
   (see `backend/Dockerfile`). Rebuild the backend image so the served callable is the wrapped
   ASGI app (the trace-query fallback depends on it).
3. **Stray `.gitignore` commit on `main`.** Commit `3c46425` ("remove claude.sh from .gitignore")
   rode into the merge. It is your own pre-existing local edit, committed by the active
   auto-committer (see Warning), NOT part of this task. Revert it if unwanted:
   `git revert 3c46425` (disable the auto-committer first, or it may re-add the change).
4. **Harmless dead comment**: `backend/pyproject.toml:48` still mentions `app.main:app`. It is a
   comment, not an active entrypoint. Clean up when convenient.

## Warning: auto-commit process
An auto-commit process is active in this session (it authored `3c46425` on its own; it is not a
`.git/hooks` script — likely a Claude Code hook or `graft`). During this session it committed a
pending `.gitignore` edit by itself. Decide whether to keep it; it fights branch-hygiene rebases.

## Key files to read first
- `CONTEXT.md` — dated changelog; the last section covers this consolidation step by step.
- `app/services/agent_proxy.py` and `app/routers/agent_proxy.py` — the new proxy.
- `docs/superpowers/specs/2026-08-17-agent-proxy-mcp-backend-consolidation-design.md` — the spec.
