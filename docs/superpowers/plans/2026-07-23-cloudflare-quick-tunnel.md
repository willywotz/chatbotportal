# Cloudflare Quick Tunnel for Dev — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the local dev stack a temporary public `https://` URL so the running site can be shared with teammates and testers, with the URL printed automatically on startup.

**Architecture:** An always-on `cloudflared` service in the dev-only compose override opens an outbound-only Quick Tunnel to `nginx:8080`, so the shared URL exercises the same `nginx/routes.conf` contract production uses. A one-shot `tunnel-url` sidecar polls cloudflared's metrics endpoint and prints the randomly assigned hostname. Nothing in `docker-compose.yaml`, `nginx/`, or the certbot TLS path changes.

**Tech Stack:** Docker Compose, `cloudflare/cloudflared`, `alpine` + BusyBox `wget`, POSIX `sh`, Vite 5.4.21, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-07-23-cloudflare-quick-tunnel-design.md`

**Branch:** `feat/cloudflare-quick-tunnel` (already created, off `dev`)

## Global Constraints

- All changes are **dev-only**. Do not modify `docker-compose.yaml`, `nginx/`, or the certbot/Let's Encrypt path.
- Both new images track **`latest`** (`cloudflare/cloudflared:latest`, `alpine:latest`) — this is deliberate, per the spec's Image-tag policy. Do not "fix" them to pinned tags.
- The tunnel URL is **random per restart**. Nothing may hardcode a hostname.
- Vite host matching uses the leading-dot suffix form `".trycloudflare.com"` — not a wildcard, not a bare hostname.
- Shell code is **POSIX `sh`**, not bash. No `[[ ]]`, no arrays, no `local`.
- The metrics port `2000` is container-internal only. Never add it to a `ports:` block.
- TDD is mandatory: write the failing test, confirm it fails, then implement.
- Follow the repo's existing comment style — explain *why*, not *what*.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `scripts/tunnel-url.sh` | Create | Poll cloudflared's metrics endpoint, print the tunnel URL. The only component with real logic. |
| `scripts/tunnel-url_test.sh` | Create | Dependency-free POSIX test for the above, against a stub HTTP server. |
| `docker-compose.override.yaml` | Modify | Add `cloudflared` and `tunnel-url` services. |
| `frontend/vite.config.ts` | Modify | Add `server.allowedHosts` so Vite accepts tunnelled requests. |
| `frontend/src/test/vite-config.test.ts` | Create | Regression guard on `allowedHosts`. |
| `.github/workflows/test.yml` | Modify | Add a `scripts` job running the shell test. |
| `docs/quickstart.md` | Modify | Tunnel row in the origins table, sharing + troubleshooting notes. |
| `CONTEXT.md` | Modify | Record the feature, per the repo's CLAUDE.md rule. |

`scripts/` does not exist yet; Task 1 creates it.

---

## Task 1: Tunnel URL script

The poll-and-parse logic plus its test. Lives in a real file rather than inline YAML precisely so it is testable.

**Files:**
- Create: `scripts/tunnel-url.sh`
- Create: `scripts/tunnel-url_test.sh`
- Modify: `.github/workflows/test.yml` (add a `scripts` job)

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `scripts/tunnel-url.sh [BASE_URL]` — `BASE_URL` defaults to `http://cloudflared:2000`. On success prints a banner line containing `https://<hostname>` to **stdout** and exits `0`. On timeout prints a diagnostic to **stderr** and exits `1`. Honors `TUNNEL_URL_TIMEOUT` (seconds, default `60`). Task 3 mounts this file at `/tunnel-url.sh` and runs it with `sh`.

- [ ] **Step 1: Write the failing test**

Create `scripts/tunnel-url_test.sh`:

```sh
#!/usr/bin/env sh
# Tests scripts/tunnel-url.sh against a stub HTTP server standing in for
# cloudflared's metrics endpoint. No test framework: this is the only shell
# script in the repo, so a bats dependency would cost more than it saves.
set -eu

dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
script="$dir/tunnel-url.sh"
failures=0

for cmd in python3 wget; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "tunnel-url_test: $cmd is required to run these tests" >&2
    exit 1
  }
done

free_port() {
  python3 -c 'import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()'
}

# Serves $1 as the body of /quicktunnel. Sets $stub_base for the caller.
start_stub() {
  stub_dir=$(mktemp -d)
  printf '%s' "$1" > "$stub_dir/quicktunnel"
  stub_port=$(free_port)
  python3 -m http.server "$stub_port" --bind 127.0.0.1 \
    --directory "$stub_dir" >/dev/null 2>&1 &
  stub_pid=$!
  stub_base="http://127.0.0.1:$stub_port"
  # Block until the listener accepts, otherwise the first poll races startup
  # and the "valid response" case flakes.
  i=0
  while [ "$i" -lt 50 ]; do
    wget -qO- "$stub_base/quicktunnel" >/dev/null 2>&1 && return 0
    i=$((i + 1))
    sleep 0.1
  done
  echo "tunnel-url_test: stub server never came up" >&2
  exit 1
}

stop_stub() {
  [ -n "${stub_pid:-}" ] && kill "$stub_pid" 2>/dev/null || true
  [ -n "${stub_dir:-}" ] && rm -rf "$stub_dir"
  stub_pid=
  stub_dir=
}

check() {
  if [ "$2" = "$3" ]; then
    echo "ok - $1"
  else
    echo "FAIL - $1: expected [$3], got [$2]" >&2
    failures=$((failures + 1))
  fi
}

# --- valid response ---------------------------------------------------------
start_stub '{"hostname":"abc.trycloudflare.com"}'
out=$(TUNNEL_URL_TIMEOUT=5 sh "$script" "$stub_base") && status=0 || status=$?
stop_stub
check "valid response prints the URL" \
  "$(printf '%s' "$out" | grep -c 'https://abc\.trycloudflare\.com')" "1"
check "valid response exits 0" "$status" "0"

# --- malformed body ---------------------------------------------------------
start_stub 'not json at all'
out=$(TUNNEL_URL_TIMEOUT=2 sh "$script" "$stub_base" 2>/dev/null) \
  && status=0 || status=$?
stop_stub
check "malformed body exits 1" "$status" "1"
check "malformed body prints nothing on stdout" "$out" ""

# --- unreachable endpoint ---------------------------------------------------
dead_base="http://127.0.0.1:$(free_port)"
out=$(TUNNEL_URL_TIMEOUT=2 sh "$script" "$dead_base" 2>/dev/null) \
  && status=0 || status=$?
check "unreachable endpoint exits 1" "$status" "1"

# --- diagnostics go to stderr, keeping stdout pipe-safe ---------------------
err=$(TUNNEL_URL_TIMEOUT=2 sh "$script" "$dead_base" 2>&1 >/dev/null) || true
check "timeout message goes to stderr" \
  "$(printf '%s' "$err" | grep -c 'no hostname')" "1"

if [ "$failures" -ne 0 ]; then
  echo "$failures test(s) failed" >&2
  exit 1
fi
echo "all tunnel-url tests passed"
```

Make it executable:

```bash
chmod +x scripts/tunnel-url_test.sh
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./scripts/tunnel-url_test.sh`

Expected: FAIL — the script under test does not exist yet, so `sh "$script"` errors and every `check` reports a mismatch. Output ends with a non-zero exit and `test(s) failed`.

- [ ] **Step 3: Write the minimal implementation**

Create `scripts/tunnel-url.sh`:

```sh
#!/usr/bin/env sh
# Print the current Cloudflare Quick Tunnel URL.
#
# Quick Tunnels mint a new random hostname on every restart, so the URL cannot
# be configured — it has to be read back from cloudflared at runtime. The
# metrics server serves it as JSON at /quicktunnel, which is stabler than
# scraping the startup banner out of the logs.
#
# The base URL is a parameter so the tests can point at a stub server.
set -eu

base="${1:-http://cloudflared:2000}"
timeout="${TUNNEL_URL_TIMEOUT:-60}"

i=0
while [ "$i" -lt "$timeout" ]; do
  # wget exits non-zero when cloudflared is not up yet, but it sits in a
  # pipeline whose status is sed's, so `set -e` does not trip here: a failed
  # fetch falls through to an empty $host and we simply poll again.
  host=$(wget -qO- "$base/quicktunnel" 2>/dev/null \
    | sed -n 's/.*"hostname":"\([^"]*\)".*/\1/p')
  if [ -n "$host" ]; then
    printf '\n=== DEV TUNNEL: https://%s ===\n\n' "$host"
    exit 0
  fi
  i=$((i + 1))
  sleep 1
done

echo "tunnel-url: no hostname from $base after ${timeout}s" >&2
exit 1
```

Make it executable:

```bash
chmod +x scripts/tunnel-url.sh
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./scripts/tunnel-url_test.sh`

Expected: PASS — six `ok -` lines followed by `all tunnel-url tests passed`, exit 0.

- [ ] **Step 5: Add the CI job**

In `.github/workflows/test.yml`, append a fourth job after the existing `frontend` job, matching the file's existing style (pinned action SHA, same checkout ref as the other jobs):

```yaml
  scripts:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6.0.3
      - run: ./scripts/tunnel-url_test.sh
```

- [ ] **Step 6: Verify the workflow file still parses**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/test.yml')); print('ok')"`

Expected: `ok`

- [ ] **Step 7: Commit**

```bash
rtk git add scripts/tunnel-url.sh scripts/tunnel-url_test.sh .github/workflows/test.yml
rtk git commit -m "feat(dev): add tunnel-url script to read the Quick Tunnel hostname"
```

---

## Task 2: Vite allowedHosts

Without this, every tunnelled request returns `Blocked request. This host is not allowed.` — Vite 5.4.21 carries the backported host check. This task is independent of the tunnel itself and testable on its own.

**Files:**
- Modify: `frontend/vite.config.ts`
- Create: `frontend/src/test/vite-config.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: dev server accepts any `*.trycloudflare.com` Host header. No exported symbols.

Note: `frontend/vitest.config.ts` sets `include: ["src/**/*.{test,spec}.{ts,tsx}"]`, so the test **must** live under `frontend/src/` — a test placed next to `vite.config.ts` would be silently skipped.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/vite-config.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import viteConfig from "../../vite.config";

describe("vite config", () => {
  it("allows tunnelled hosts so Quick Tunnel URLs are not blocked", () => {
    // The config export is a function of the Vite env. Resolve it in
    // production mode: `allowedHosts` is mode-independent, and development
    // mode additionally loads lovable-tagger, which this test does not need.
    const config = viteConfig({ mode: "production", command: "serve" });

    // Leading dot = domain-suffix match, which is what makes this survive the
    // hostname changing on every tunnel restart.
    expect(config.server?.allowedHosts).toContain(".trycloudflare.com");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && rtk npx vitest run src/test/vite-config.test.ts`

Expected: FAIL — `expected undefined to contain ".trycloudflare.com"`, because `server.allowedHosts` is not set yet.

- [ ] **Step 3: Write the minimal implementation**

In `frontend/vite.config.ts`, add `allowedHosts` to the existing `server` block. The full block becomes:

```ts
  server: {
    host: "::",
    port: 8080,
    // Vite 5.4.12+ rejects unknown Host headers. The leading dot is a
    // domain-suffix match, so this survives the Quick Tunnel hostname
    // changing on every restart. Dev server only; builds ignore `server`.
    allowedHosts: [".trycloudflare.com"],
    hmr: {
      overlay: false,
    },
  },
```

Leave `host`, `port`, and `hmr` exactly as they are.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && rtk npx vitest run src/test/vite-config.test.ts`

Expected: PASS — 1 test passed.

- [ ] **Step 5: Verify nothing else regressed**

Run: `cd frontend && rtk npx tsc --noEmit -p tsconfig.app.json && rtk npx vitest run`

Expected: no TypeScript errors; the full suite passes.

- [ ] **Step 6: Commit**

```bash
rtk git add frontend/vite.config.ts frontend/src/test/vite-config.test.ts
rtk git commit -m "feat(frontend): allow *.trycloudflare.com hosts on the dev server"
```

---

## Task 3: Compose services

Wires the tunnel itself. Depends on Task 1 (mounts `scripts/tunnel-url.sh`) and Task 2 (without `allowedHosts` the end-to-end check in Step 4 would fail).

**Files:**
- Modify: `docker-compose.override.yaml`

**Interfaces:**
- Consumes: `scripts/tunnel-url.sh` from Task 1, mounted read-only at `/tunnel-url.sh`.
- Produces: service `cloudflared` (metrics on container-internal port `2000`) and one-shot service `tunnel-url`.

- [ ] **Step 1: Add both services**

Append to `docker-compose.override.yaml`, after the existing `frontend` service. Keep the file's existing two-space indentation and blank line between services.

```yaml
  # Always-on dev tunnel: publishes the gateway on a random
  # https://*.trycloudflare.com URL so the running stack can be shared. The
  # connection is outbound-only, so no port is published and no Cloudflare
  # account or DNS record is involved.
  #
  # Tracks `latest` on purpose: cloudflared is a client of a moving remote
  # service and Cloudflare deprecates old clients server-side, so a stale pin
  # eventually fails to connect in ways that look like a local bug.
  # `--no-autoupdate` still applies — self-updating inside an ephemeral
  # container just causes surprise restarts; re-pull the image instead.
  cloudflared:
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    command: tunnel --no-autoupdate --url http://nginx:8080 --metrics 0.0.0.0:2000
    networks:
      - chatbot-network
    depends_on:
      - nginx

  # Prints the tunnel URL once and exits. The hostname is random per restart,
  # so it has to be read back from cloudflared's metrics server rather than
  # configured. Re-run on demand with:
  #   docker compose run --rm --no-deps tunnel-url
  tunnel-url:
    image: alpine:latest
    restart: "no"
    networks:
      - chatbot-network
    depends_on:
      - cloudflared
    volumes:
      - ./scripts/tunnel-url.sh:/tunnel-url.sh:ro
    entrypoint: ["sh", "/tunnel-url.sh"]
```

- [ ] **Step 2: Verify the compose file is valid**

Run: `rtk docker compose config --quiet && echo ok`

Expected: `ok`, no errors. This resolves both compose files together and will reject an indentation or key mistake.

- [ ] **Step 3: Confirm both services are recognised**

Run: `rtk docker compose config --services`

Expected: the existing services plus `cloudflared` and `tunnel-url`.

- [ ] **Step 4: End-to-end check**

```bash
rtk docker compose up -d
rtk docker compose logs tunnel-url
```

Expected: the logs contain a `=== DEV TUNNEL: https://<something>.trycloudflare.com ===` banner.

Then, substituting that URL:

```bash
rtk curl -s -o /dev/null -w '%{http_code}\n' https://<host>.trycloudflare.com/
rtk curl -s -o /dev/null -w '%{http_code}\n' https://<host>.trycloudflare.com/openapi.json
```

Expected: `200` for the SPA — this is what confirms Task 2's `allowedHosts` works; a `403` carrying `Blocked request. This host is not allowed.` means it did not take effect. And `200` for `/openapi.json`, confirming backend routing through the tunnel.

Use `/openapi.json`, **not** `/health`. The backend does serve `/health` (`backend/app/main.py:162`), but `nginx/routes.conf` only proxies `/(api|sse|messages|mcp|docs|redoc|openapi.json)` to the backend, so `/health` falls through to the SPA and would return a misleading `200` from the frontend.

- [ ] **Step 4b: Confirm HMR survives the tunnel**

Open the tunnel URL in a browser, then edit any visible string under `frontend/src/`.

Expected: the change hot-reloads without a full page refresh, and the browser console shows no failed `wss://` connection. This exercises the WebSocket upgrade path through Cloudflare and `nginx`'s `location /`.

- [ ] **Step 5: Confirm on-demand re-print works**

Run: `rtk docker compose run --rm --no-deps tunnel-url`

Expected: the same URL printed again, and `docker compose ps` shows `cloudflared` still running with no restart — `--no-deps` must not disturb the tunnel.

- [ ] **Step 6: Tear down**

Run: `rtk docker compose down`

- [ ] **Step 7: Commit**

```bash
rtk git add docker-compose.override.yaml
rtk git commit -m "feat(dev): tunnel the gateway via an always-on Cloudflare Quick Tunnel"
```

---

## Task 4: Documentation

**Files:**
- Modify: `docs/quickstart.md`
- Modify: `CONTEXT.md`

**Interfaces:**
- Consumes: the behavior built in Tasks 1–3.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Add the tunnel row to the origins table**

In `docs/quickstart.md`, in the `## Base URL` table (around line 60), add a third row after the `Deployed` row:

```markdown
| Shared dev tunnel | `https://<random>.trycloudflare.com` — printed on startup by the `tunnel-url` service. Random per restart; see "Sharing a dev environment" below. |
```

- [ ] **Step 2: Add the sharing section**

Immediately after that table's paragraph (before the `---` that precedes `## Endpoints`), add:

```markdown
### Sharing a dev environment

`docker compose up` opens a Cloudflare Quick Tunnel and prints the public URL:

```
=== DEV TUNNEL: https://fuzzy-mango-plate-cat.trycloudflare.com ===
```

After `docker compose up -d`, or once the tunnel has restarted and minted a new
hostname, re-print it with:

```bash
docker compose run --rm --no-deps tunnel-url
```

`--no-deps` matters: without it Compose restarts `cloudflared` and changes the very
URL you asked for.

**The URL is public and unauthenticated.** Anyone with the link reaches the whole
dev gateway — including `/jaeger`, `/docs`, `/redoc`, and `/openapi.json`. The
hostname is random, unguessable, unindexed, and dies with the container, but it is
not access control. Do not point it at data you would not hand to the recipient,
and do not paste it anywhere public. If you need a hardened share, use a named
Cloudflare Tunnel with Access policies instead — a different feature, not set up
here.

The URL changes on every tunnel restart, so it is unsuitable for webhooks or OAuth
redirect URIs.

**Troubleshooting.** `cloudflared` tracks the `latest` image tag, but `docker
compose up` does not re-pull on its own, so a machine can sit on a months-old
build and drift from a teammate's. If the tunnel fails to connect, refresh it:

```bash
docker compose pull cloudflared && docker compose up -d cloudflared
```
```

- [ ] **Step 3: Verify the docs render**

Run: `rtk grep -n 'trycloudflare' docs/quickstart.md`

Expected: matches in both the table row and the new section. Confirm by eye that the nested code fences are balanced and the section sits before `## Endpoints`.

- [ ] **Step 4: Update CONTEXT.md**

Per the repo's CLAUDE.md rule, record the feature in `CONTEXT.md`. Read the file first and follow its existing structure and heading style rather than appending a stray section. Cover, in the style already used there:

- Dev-only Cloudflare Quick Tunnel, always-on in `docker-compose.override.yaml`, tunnels `nginx:8080`.
- `scripts/tunnel-url.sh` reads the random hostname from cloudflared's metrics endpoint; the `tunnel-url` sidecar prints it at startup.
- `frontend/vite.config.ts` sets `server.allowedHosts: [".trycloudflare.com"]`, which is required for tunnelled requests to reach Vite.
- Dev-override images track `latest` by policy; `docker-compose.yaml` stays pinned.
- The tunnel URL is public and unauthenticated.

- [ ] **Step 5: Commit**

```bash
rtk git add docs/quickstart.md CONTEXT.md
rtk git commit -m "docs: document the dev Cloudflare Quick Tunnel"
```

---

## Done

Full verification before opening a PR:

```bash
./scripts/tunnel-url_test.sh
cd frontend && rtk npx vitest run && rtk npx tsc --noEmit -p tsconfig.app.json && cd ..
rtk docker compose config --quiet && echo compose-ok
```

All three must pass. Then confirm the end-to-end behavior from Task 3 Step 4 once more against a freshly started stack.
