# Deploy BuildKit cache — observation handoff

**Branch/PR:** `perf/deploy-buildkit-cache` → `main`
**Date:** 2026-07-28
**Status:** merged, awaiting real-runner data

## What this changed and why

Deploy (`docker compose up -d --build` on the self-hosted runner) usually took
~112–120s but occasionally spiked to ~145s. Root cause: BuildKit
`--mount=type=cache` dirs (uv / go-mod / pnpm / go-build) are **builder-local** and
get wiped by `docker system prune`, disk GC, or a daemon restart, forcing a full
dependency reinstall on the next deploy.

Two fixes:

1. **Persistent layer cache** — `docker-compose.cache.yaml` (deploy-only overlay)
   exports per-service **layer** cache to `${BUILDCACHE_DIR}/<svc>` on the host
   (`type=local,mode=max`). Layer cache *can* be exported (unlike cache mounts), so
   an unchanged lockfile restores the whole dep-install layer even on a cold builder.
   Requires `COMPOSE_BAKE=true` + a container-driver buildx builder (both set up in
   `deploy.yml`).
2. **Incremental Vite** — `frontend/Dockerfile` mounts `/app/node_modules/.vite`.
   Minor (Rollup production builds don't cache incrementally without a plugin); the
   real frontend win is Fix 1 skipping `pnpm install`.

Files: `docker-compose.cache.yaml` (new), `.github/workflows/deploy.yml`,
`frontend/Dockerfile`, `context.md`.

## Baseline (pre-change deploy totals)

| Run | Total | Title |
|-----|-------|-------|
| 30324728205 | 124s | Hide test-action connection logs |
| 30321425541 | 120s | Cookie session auth + unified chat |
| 30238663757 | 145s | Cross-service tracing (spike) |
| 30211164046 | 119s | Chat pipeline transparency |
| 30138346515 | 118s | scale chat text via font-size |

Everything but `docker compose up -d --build` is trivial, so total ≈ build time.

## What to expect

- **First deploy after merge is SLOWER, not faster.** It bootstraps the
  `docker-container` builder (pulls a buildkit image) and writes a cold cache. Judge
  from the **2nd deploy onward**.
- **Steady state (unchanged lockfiles):** dep-install layers restored from
  `$HOME/deploy-buildcache` → no uv/go/pnpm reinstall. Expect the tail spikes
  (~145s) to disappear; warm builds at/below the ~112–118s floor.
- **Fixed floor remains** (~30–50s): healthcheck `start_period`/`interval` chain
  (postgres → backend → nginx). Not addressed here — separate lever if needed.

## How to observe

```bash
# Recent deploy runs + per-run total
rtk gh run list --workflow=deploy.yml -L 10
rtk gh run view <run-id> --json createdAt,updatedAt,displayTitle

# On the runner: confirm builder + cache are live
docker buildx ls | grep deploy                 # container-driver builder present
du -sh "$HOME/deploy-buildcache"/*             # cache dirs populating (non-trivial size)
```

In the "Build and deploy" step log, a warm hit shows `CACHED` on the
`uv sync` / `go mod download` / `pnpm install` steps instead of re-running them.

## Success criteria

- [ ] 2nd+ deploys show `CACHED` on dependency-install steps (unchanged lockfiles).
- [ ] No more ~145s spikes across ~5 consecutive deploys.
- [ ] `$HOME/deploy-buildcache/{backend,agent-proxy,frontend}` populated on the runner.

## Rollback

Revert the merge commit, or minimally: drop `-f docker-compose.cache.yaml`,
`COMPOSE_BAKE`, and `BUILDX_BUILDER` from the "Build and deploy" step in
`deploy.yml`. The base `docker-compose.yaml` is unchanged, so this reverts cleanly
to the prior behavior.

## Open follow-ups

- **`mode=max` cache grows unbounded** — periodically prune `$HOME/deploy-buildcache`
  (or add a size cap). Not urgent.
- **Runner path writability** — assumes the runner user can write `$HOME`. If the
  "Prepare persistent build cache" step fails on `mkdir`, point `BUILDCACHE_DIR` at a
  known-writable path.
- **Real Vite incrementality** would need a Rollup/Vite persistent-cache plugin —
  separate change if frontend build time is still a concern after Fix 1.
- **Healthcheck floor** — tightening `start_period`/`interval` on backend/agent-proxy
  is the next lever if deploys need to go below ~110s.
