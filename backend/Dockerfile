from python:3.12-slim-trixie as base
copy --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

from base as development
run apt-get update && apt-get install -y wget && rm -rf /var/lib/apt/lists/*
workdir /app
env UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
copy pyproject.toml uv.lock ./
run --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project
copy . .
cmd ["uv", "run", "fastapi", "dev", "--host", "0.0.0.0", "--port", "8080"]

from base as production
run apt-get update && apt-get install -y wget ca-certificates && rm -rf /var/lib/apt/lists/*
workdir /app
env UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1
copy pyproject.toml uv.lock ./
run --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project
copy . .
cmd ["uv", "run", "uvicorn", "app.main:asgi_app", "--host", "0.0.0.0", "--port", "8080", "--workers", "4"]
