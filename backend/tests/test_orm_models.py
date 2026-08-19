from sqlalchemy import Enum as SAEnum, UniqueConstraint

from app.models.agency import Agency, AgencyStatus, ConnectionType
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.event import DomainEvent
from app.models.executive_brief import ExecutiveBrief
from app.models.llm_provider import LlmProvider
from app.models.llm_usage import LlmUsage
from app.models.rate_limit_counter import RateLimitCounter
from app.models.setting import Setting


def test_agency_table_and_columns():
    t = Agency.__table__
    assert t.name == "agencies"
    assert t.c.id.primary_key
    assert t.c.connection_type.default.arg == ConnectionType.API
    assert t.c.status.default.arg == AgencyStatus.active
    assert isinstance(t.c.connection_type.type, SAEnum)
    assert t.c.connection_type.type.length == 10
    assert t.c.status.type.length == 20
    assert "agencies" in Base.metadata.tables


def test_audit_log_table_and_columns():
    t = AuditLog.__table__
    assert t.name == "audit_logs"
    assert t.c.id.primary_key
    assert t.c.actor_id.nullable
    assert t.c.detail.nullable


def test_domain_event_table_and_columns():
    t = DomainEvent.__table__
    assert t.name == "domain_events"
    assert t.c.id.primary_key
    assert t.c.event_type.type.length == 100
    assert t.c.payload.default.is_callable
    assert not t.c.payload.nullable
    assert t.c.dispatched_at.nullable


def test_executive_brief_table_and_columns():
    t = ExecutiveBrief.__table__
    assert t.name == "executive_briefs"
    assert t.c.id.primary_key
    assert t.c.content.default.arg == ""
    assert t.c.status.default.arg == "ok"


def test_llm_provider_table_and_columns():
    t = LlmProvider.__table__
    assert t.name == "llm_providers"
    assert t.c.id.primary_key
    assert t.c.name.unique
    assert t.c.timeout_seconds.default.arg == 60.0


def test_llm_usage_table_and_columns():
    t = LlmUsage.__table__
    assert t.name == "llm_usage"
    assert t.c.id.primary_key
    assert t.c.user_id.nullable
    assert LlmUsage(prompt_tokens=2, completion_tokens=3).total_tokens == 5


def test_setting_table_and_columns():
    t = Setting.__table__
    assert t.name == "settings"
    assert t.c.key.primary_key
    assert "id" not in t.c


def test_rate_limit_counter_table_and_columns():
    t = RateLimitCounter.__table__
    assert t.name == "rate_limit_counters"
    assert t.c.id.primary_key
    assert t.c.id.autoincrement is True
    unique = [c for c in t.constraints if isinstance(c, UniqueConstraint)]
    assert any({col.name for col in c.columns} == {"key", "window_start"} for c in unique)
