# Local development

The dev stack is the prod stack with one swap: the `development` Dockerfile
stages (hot-reload servers instead of production servers). A
`docker-compose.override.yaml` targets those stages and wires Compose
`develop.watch` to sync source edits into the running containers — **no
bind-mounts**, so no WSL2 cross-filesystem issues or host `node_modules`
clobbering.

The override is **never** merged into prod — `deploy.yml` runs
`docker compose -f docker-compose.yaml up`, and an explicit `-f` disables
override merging.

## Prerequisites

- Docker + the Compose plugin.
- Ports `8080` (gateway) and `5432` (postgres) free on the host, or set
  `EXTERNAL_HTTP_PORT` / `EXTERNAL_POSTGRES_PORT` in `.env`.

## First run

```bash
cp .env.example .env          # if you don't have one
docker compose up --watch --build   # builds dev images, starts stack, begins syncing
```

Reach the app at `http://localhost:${EXTERNAL_HTTP_PORT}` (8080 by default).
Traffic enters Caddy, which proxies `/` → frontend and `/api` → backend — the
same routing contract as prod, just plain HTTP (no `CERT_DOMAIN` set).

## Hot-reload

Hot-reload only activates with `--watch`. A plain `docker compose up` runs the
baked dev image fine, but edits on the host are **not** synced into the
container — always use `--watch` for development.

`develop.watch` has three actions, each scoped to a path:

| Action | When | Effect |
|---|---|---|
| `sync` | Source edits (`backend/app`, `frontend/src`) | File is copied into the container. The dev server then reloads: backend `watchfiles` restarts uvicorn; frontend Vite pushes an HMR update. |
| `sync+restart` | `backend/migrations` | File copied, then the process restarted (a migration needs a restart to apply). |
| `rebuild` | Dependency manifests (`pyproject.toml`/`uv.lock`, `package.json`/`pnpm-lock.yaml`) | Image rebuilt and container recreated — `sync` can't add packages. |

So: edit a `.py` or `.tsx` → instant reload. Change a dependency manifest →
Compose rebuilds that service automatically.

## Day-to-day

```bash
docker compose up --watch          # start + sync (the normal dev command)
docker compose up --watch --build  # force-rebuild images (after big changes)
docker compose down                # stop
docker compose logs -f backend frontend   # tail dev-server output
```

## Reaching individual services

The gateway is the normal entry point, but for debugging you can hit services
directly. Add `EXTERNAL_POSTGRES_PORT=5432` to `.env` to expose postgres.
Backend and frontend are not published to the host by default — reach them
through Caddy, or `docker compose exec backend wget -qO- http://localhost:8080/health`.

## Running tests

Tests run on the host, not in the dev stack:

```bash
# Backend
cd backend && uv sync && uv run pytest

# Frontend
cd frontend && pnpm install && pnpm test
```

## What is NOT in dev

- **No TLS.** `CERT_DOMAIN` is unset, so Caddy serves plain HTTP. To test TLS
  locally you'd need a resolvable domain + open 80/443; that's prod's job.
- **No separate database.** Dev uses the same `postgres` service (a fresh
  volume). `docker compose down -v` wipes it for a clean slate.
