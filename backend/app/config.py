import json
import logging
from dataclasses import dataclass, field
from typing import get_origin
from urllib.parse import parse_qs, unquote, urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


@dataclass
class OverrideReport:
    applied: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)

DEFAULT_JWT_SECRET = "change-me-in-production-use-a-long-random-string"


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "AI Chatbot Portal API"
    APP_VERSION: str = "1.0.0"
    TIMEZONE: str = "Asia/Bangkok"
    USER_AGENT_PREFIX: str = "AI-Chatbot-Portal/1.0"
    ENV: str = "development"  # development | production

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgres://postgres:postgres@localhost:5432/chatbot"

    # ── Database pool ─────────────────────────────────────────────────────────
    DB_POOL_MIN: int = 1
    DB_POOL_MAX: int = 10

    # ── Uploads ──────────────────────────────────────────────────────────────
    # Single source of truth for on-disk upload storage (named Docker volume in
    # docker-compose.yaml, backend service only). Agency logos live under
    # {UPLOAD_DIR}/agency-logos/.
    UPLOAD_DIR: str = "/app/uploads"

    # ── Redis (shared LLM-provider throttle budget across workers) ───────────
    REDIS_URL: str = ""           # empty = in-process limiter (single worker)
    REDIS_SOCKET_TIMEOUT_MS: int = 100

    # ── CORS ─────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["*"]  # bypass all origins by default

    # ── Auth ─────────────────────────────────────────────────────────────────
    JWT_SECRET: str = DEFAULT_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    MIN_PASSWORD_LENGTH: int = 6

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
    ONECHAT_V3_URL: str = "http://185.84.160.55:8000/v3/chat"
    ONECHAT_V4_URL: str = "http://185.84.160.55:8000/v4/chat"
    ONECHAT_V5_URL: str = "http://185.84.160.55:8000/v5/chat"
    CHAT_STREAM_VERSION: str = "v5"        # "v4" | "v5" — upstream for POST /chat/stream
    MCP_ENDPOINT_URL: str = "http://185.84.161.145/mcp/"

    # ── Chat ─────────────────────────────────────────────────────────────────
    A2A_DISPATCH_TIMEOUT: int = 30
    V4_STREAM_TIMEOUT: float = 300.0
    EXTERNAL_CHAT_TIMEOUT: float = 180.0
    TITLE_MAX_LENGTH: int = 50
    PREVIEW_MAX_LENGTH: int = 100
    SPEC_TEXT_MAX_CHARS: int = 30000
    RESPONSES_WS_MAX_CONNECTIONS: int = 1024
    RESPONSES_WS_MAX_DURATION_SECONDS: int = 900

    # ── Agency health / scheduler ────────────────────────────────────────────
    AGENCY_CHAT_TIMEOUT: int = 180
    AGENCY_CHAT_CONCURRENCY: int = 5
    HEALTH_CHECK_INTERVAL_MINUTES: int = 15
    CONNECTION_TEST_TIMEOUT: float = 10.0
    HEALTH_DEGRADED_UPTIME_PCT: float = 95.0
    CONNECTION_LOG_BODY_MAX_CHARS: int = 4096
    CONNECTION_LOG_RETENTION_DAYS: int = 90
    EVAL_INTERVAL_HOURS: int = 168  # weekly

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

    # ── Embedding / similarity ──────────────────────────────────────────────
    SIMILARITY_THRESHOLD: float = 0.95
    SIMILARITY_WINDOW_SECONDS: int = 60
    SIMILARITY_CACHE_ENABLED: bool = True

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


def assert_production_secrets(s: "Settings") -> None:
    if s.ENV.strip().lower() == "production" and s.JWT_SECRET == DEFAULT_JWT_SECRET:
        raise RuntimeError("JWT_SECRET must be changed when ENV=production")


SETTINGS_GROUPS: dict[str, list[str]] = {
    "Similarity": ["SIMILARITY_THRESHOLD", "SIMILARITY_WINDOW_SECONDS", "SIMILARITY_CACHE_ENABLED"],
    # "App": ["APP_NAME", "APP_VERSION", "TIMEZONE", "USER_AGENT_PREFIX", "ENV"],
    "OneChat": ["CHAT_STREAM_VERSION", "MCP_ENDPOINT_URL", "ONECHAT_V3_URL", "ONECHAT_V4_URL", "ONECHAT_V5_URL"],
    # "Chat": ["A2A_DISPATCH_TIMEOUT", "V4_STREAM_TIMEOUT", "EXTERNAL_CHAT_TIMEOUT", "TITLE_MAX_LENGTH", "PREVIEW_MAX_LENGTH", "SPEC_TEXT_MAX_CHARS", "RESPONSES_WS_MAX_CONNECTIONS", "RESPONSES_WS_MAX_DURATION_SECONDS"],
    # "Agency health": ["AGENCY_CHAT_TIMEOUT", "AGENCY_CHAT_CONCURRENCY", "HEALTH_CHECK_INTERVAL_MINUTES", "CONNECTION_TEST_TIMEOUT", "HEALTH_DEGRADED_UPTIME_PCT", "CONNECTION_LOG_BODY_MAX_CHARS", "CONNECTION_LOG_RETENTION_DAYS", "EVAL_INTERVAL_HOURS"],
}

SECRET_FIELD_NAMES: set[str] = {
    "JWT_SECRET", "OPENROUTER_API_KEY", "PARSE_SPEC_API_KEY",
}

settings = Settings()


async def load_settings_from_db() -> None:
    from app.models.setting import Setting as SettingModel
    rows = await SettingModel.all()
    overrides = {row.key: row.value for row in rows}
    settings.apply_overrides(overrides)


def _build_tortoise_orm(s: "Settings") -> dict:
    """Build Tortoise ORM config with asyncpg pool sizing for Postgres connections."""
    _parsed = urlparse(s.DATABASE_URL)

    if not _parsed.hostname:
        raise ValueError(
            f"DATABASE_URL is malformed (no hostname): {s.DATABASE_URL!r}"
        )

    # Parse query string; map sslmode -> ssl (asyncpg connect() accepts ssl="require" etc.).
    # All other params (e.g. sslcert, sslrootcert) are forwarded as-is.
    query_params: dict = {}
    for key, values in parse_qs(_parsed.query).items():
        val = values[-1]
        query_params["ssl" if key == "sslmode" else key] = val

    credentials: dict = {
        "host": _parsed.hostname,
        "port": _parsed.port or 5432,
        "user": unquote(_parsed.username or ""),
        "password": unquote(_parsed.password or ""),
        "database": _parsed.path.lstrip("/"),
        "minsize": s.DB_POOL_MIN,
        "maxsize": s.DB_POOL_MAX,
        **query_params,
    }
    return {
        "connections": {
            "default": {
                "engine": "tortoise.backends.asyncpg",
                "credentials": credentials,
            }
        },
        "apps": {
            "models": {
                "models": [
                    "app.models",
                    "aerich.models",
                ],
                "default_connection": "default",
            },
        },
    }


# Tortoise ORM config (used by aerich and register_tortoise)
TORTOISE_ORM = _build_tortoise_orm(settings)
