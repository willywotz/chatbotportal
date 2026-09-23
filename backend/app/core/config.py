import json
import logging
from dataclasses import dataclass, field
from typing import get_origin
from urllib.parse import parse_qs, urlparse, urlunparse

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


@dataclass
class OverrideReport:
    applied: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)

class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────────
    TIMEZONE: str = "Asia/Bangkok"
    USER_AGENT_PREFIX: str = "AI-Chatbot-Portal/1.0"
    LOG_LEVEL: str = "INFO"   # 15-Factor XI: log level for the stdout event stream
    EVENT_DISPATCH_INTERVAL_SECONDS: int = 10  # domain-event outbox dispatcher tick

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgres://postgres:postgres@localhost:5432/chatbot"

    # ── Database pool ─────────────────────────────────────────────────────────
    DB_POOL_MIN: int = 1
    DB_POOL_MAX: int = 10

    # ── CORS ─────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["*"]

    # ── OIDC provider (self-hosted) ──────────────────────────────────────────
    # The backend is its own OpenID Provider / IdP. OIDC_ISSUER is the PUBLIC,
    # browser-facing issuer base (through Caddy, the root origin, e.g.
    # https://<domain>). It is the `iss` every token carries and the `authority`
    # the SPA discovers, so the same value drives discovery
    # (`{issuer}/.well-known/openid-configuration`), token signing and token
    # verification, and is the access-token `aud` (single-issuer convention — no
    # separate audience knob). Flow endpoints live under `{issuer}/oauth2/*`.
    # OIDC_CLIENT_ID is the sole first-party SPA client. Lifetimes are seconds.
    # OIDC_PRIVATE_KEY is an optional PEM override; when empty the signing key is
    # generated once and persisted in the database (shared across uvicorn workers).
    OIDC_ISSUER: str = "http://localhost:8080"
    OIDC_CLIENT_ID: str = "chatbotportal-web"
    OIDC_ALLOWED_REDIRECT_URIS: list[str] = [
        "http://localhost:8080/auth/callback",
        "http://localhost:5173/auth/callback",
    ]
    OIDC_ACCESS_TOKEN_TTL: int = 900          # 15 minutes
    OIDC_REFRESH_TOKEN_TTL: int = 30 * 24 * 3600  # 30 days
    OIDC_CODE_TTL: int = 60                    # 1 minute
    OIDC_PRIVATE_KEY: str = ""

    # Startup seed for the first administrator (created only if no admin exists).
    SEED_ADMIN_EMAIL: str = "admin@chatbotportal.local"
    SEED_ADMIN_PASSWORD: str = "admin"

    # ── LLM / OpenRouter ────────────────────────────────────────────────────
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_API_URL: str = "https://openrouter.ai/api/v1/chat/completions"
    CLASSIFICATION_MODEL: str = "google/gemini-2.5-flash-lite"
    LLM_CALL_TIMEOUT: float = 60.0

    # ── Parse spec (ThaiLLM) ─────────────────────────────────────────────────
    PARSE_SPEC_URL: str = "http://thaillm.or.th/api/openthaigpt/v1/chat/completions"
    PARSE_SPEC_API_KEY: str = ""
    PARSE_SPEC_TIMEOUT: int = 60
    PARSE_SPEC_LLM_MODEL: str = "/model"

    # ── OneChat endpoints ────────────────────────────────────────────────────
    ONECHAT_BASE_URL: str = "http://185.84.160.55:8000"
    MCP_ENDPOINT_URL: str = "http://185.84.161.145/mcp/"
    # Appended as a query string to agent-proxy endpoint_url when set; used to
    # probe whether OneChat preserves query strings on its callback (empty = off).
    TRACE_URL_PROBE: str = ""

    # ── Chat ─────────────────────────────────────────────────────────────────
    A2A_DISPATCH_TIMEOUT: int = 30
    V4_STREAM_TIMEOUT: float = 300.0
    EXTERNAL_CHAT_TIMEOUT: float = 180.0
    TITLE_MAX_LENGTH: int = 50
    PREVIEW_MAX_LENGTH: int = 100
    SPEC_TEXT_MAX_CHARS: int = 30000
    CHAT_WS_MAX_CONNECTIONS: int = 1024
    CHAT_WS_MAX_DURATION_SECONDS: int = 900

    # ── Agency health / scheduler ────────────────────────────────────────────
    AGENCY_CHAT_TIMEOUT: int = 180
    HEALTH_CHECK_INTERVAL_MINUTES: int = 15
    CONNECTION_TEST_TIMEOUT: float = 10.0
    HEALTH_DEGRADED_UPTIME_PCT: float = 95.0
    CONNECTION_LOG_BODY_MAX_CHARS: int = 4096
    CONNECTION_LOG_RETENTION_DAYS: int = 90
    EVAL_INTERVAL_HOURS: int = 7 * 24

    # ── Uptime monitor ───────────────────────────────────────────────────────
    MONITOR_TICK_SECONDS: int = 15
    MONITOR_CLAIM_BATCH: int = 50
    MONITOR_PROBE_CONCURRENCY: int = 5
    DEFAULT_CHECK_INTERVAL_SECONDS: int = 300
    CHECK_JITTER_SECONDS: int = 30
    CHECK_RETRY_MAX: int = 3
    CHECK_BACKOFF_BASE_MS: int = 200
    FAILURE_THRESHOLD: int = 3
    UPTIME_BUCKET_HOUR_RETENTION_DAYS: int = 14
    UPTIME_BUCKET_DAY_RETENTION_DAYS: int = 365

    # ── Executive summary ────────────────────────────────────────────────────
    BRIEF_REGEN_INTERVAL_HOURS: int = 24
    WEEKLY_BRIEF_TIMEOUT: float = 3600.0  # 1h — effectively no limit for the weekly brief

    # ── Popular questions ────────────────────────────────────────────────────
    POPULAR_QUESTIONS_REGEN_INTERVAL_HOURS: int = 24
    POPULAR_QUESTIONS_WINDOW_DAYS: int = 30
    POPULAR_QUESTIONS_MIN_TURNS: int = 20
    POPULAR_QUESTIONS_DISPLAY_COUNT: int = 8

    # ── Analytics windows ────────────────────────────────────────────────────
    AVG_LATENCY_WINDOW_DAYS: int = 1
    FEEDBACK_TREND_DAYS: int = 14
    BUSINESS_HOURS_START: int = 8
    BUSINESS_HOURS_END: int = 18

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def apply_overrides(self, overrides: dict[str, str]) -> "OverrideReport":
        report = OverrideReport()
        for key, raw_value in overrides.items():
            field_info = self.__class__.model_fields.get(key)
            if field_info is None:
                report.unknown.append(key)
                logger.warning("ignoring unknown settings override key: %s", key)
                continue
            try:
                parsed = _deserialize(raw_value, field_info.annotation)
                object.__setattr__(self, key, parsed)
                report.applied.append(key)
            except Exception:
                report.invalid.append(key)
                logger.warning("failed to parse override %s=%r; keeping default", key, raw_value)
        return report


def _deserialize(raw: str, annotation: type):
    origin = get_origin(annotation)
    if annotation is bool:
        return raw.lower() in ("true", "1", "yes")
    if annotation is int:
        return int(raw)
    if annotation is float:
        return float(raw)
    if origin is list or annotation in (list, list[str]):
        return json.loads(raw)
    return raw


SETTINGS_GROUPS: dict[str, list[str]] = {
    "OneChat": ["MCP_ENDPOINT_URL", "ONECHAT_BASE_URL"],
}

SECRET_FIELD_NAMES: set[str] = {
    "OPENROUTER_API_KEY", "PARSE_SPEC_API_KEY",
}

settings = Settings()


async def load_settings_from_db() -> None:
    from app.core.db import AsyncSessionLocal
    from app.features.settings.repositories import setting as setting_repo

    async with AsyncSessionLocal() as session, session.begin():
        rows = await setting_repo.all(session)
    overrides = {row.key: row.value for row in rows}
    settings.apply_overrides(overrides)


def database_url(s: "Settings") -> str:
    parsed = urlparse(s.DATABASE_URL)
    if not parsed.hostname:
        raise ValueError(f"DATABASE_URL is malformed: {s.DATABASE_URL!r}")
    return urlunparse(("postgresql+asyncpg", parsed.netloc, parsed.path, "", "", ""))


def connect_args(s: "Settings") -> dict:
    parsed = urlparse(s.DATABASE_URL)
    query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
    args: dict = {}
    sslmode = query.get("sslmode")
    if sslmode:
        # withinlazy: pass libpq-style string through; asyncpg accepts
        # "require"/"prefer"/"verify-full". Upgrade to an ssl.SSLContext if
        # client-cert verification is ever required.
        args["ssl"] = sslmode
    return args
