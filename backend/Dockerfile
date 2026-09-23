FROM python:3.12-slim-trixie AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN apt-get update && apt-get install -y wget && rm -rf /var/lib/apt/lists/*
WORKDIR /app

FROM base AS development
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project
COPY . .
CMD ["uv", "run", "fastapi", "dev", "--host", "0.0.0.0", "--port", "8080"]

FROM base AS production
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project
COPY . .
HEALTHCHECK --interval=15s --timeout=10s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
CMD ["uv", "run", "uvicorn", "app.main:asgi_app", "--host", "0.0.0.0", "--port", "8080", "--workers", "4"]
