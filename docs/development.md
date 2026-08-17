# Local development

The dev stack is the prod stack with two swaps: the `development` Dockerfile
stages (hot-reload servers instead of production servers) and source
bind-mounts (host edits are live inside the containers). A `docker-compose.override.yaml`
applies both automatically, so a bare `docker compose up` runs the full dev
stack. The override is **never** merged into prod — `deploy.yml` runs
`docker compose -f docker-compose.yaml up`, and an explicit `-f` disables
override merging.

## Prerequisites

- Docker + the Compose plugin.
- Ports `8080` (gateway) and `5432` (postgres) free on the host, or set
  `EXTERNAL_HTTP_PORT` / `EXTERNAL_POSTGRES_PORT` in `.env`.

## First run

```bash
cp .env.example .env          # if you don't have one
docker compose up --build     # builds the dev images, starts the stack
```

Reach the app at `http://localhost:${EXTERNAL_HTTP_PORT}` (8080 by default).
Traffic enters Caddy, which proxies `/` → frontend and `/api` → backend — the
same routing contract as prod, just plain HTTP (no `CERT_DOMAIN` set).

## Hot-reload

| Service | How | What reloads |
|---|---|---|
| frontend | Vite dev server (HMR) | Edits to `frontend/src/**` appear in the browser instantly, no full reload. |
| backend | `fastapi dev` (`--reload`) | Edits to `backend/app/**/*.py` restart uvicorn automatically (single worker). |

Both work because the override bind-mounts `./backend` and `./frontend` into
the containers — save a file on the host, the change is live inside.

## Day-to-day

```bash
docker compose up             # start (images already built)
docker compose up --build     # start + rebuild images (after dep changes)
docker compose down           # stop
docker compose logs -f backend frontend   # tail dev-server output
```

When you change dependencies (`pyproject.toml`/`uv.lock`, `package.json`/
`pnpm-lock.yaml`), rebuild: `docker compose up --build backend` (or `frontend`).
Hot-reload only watches source, not dependency manifests.

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
