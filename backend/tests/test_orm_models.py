from sqlalchemy import Enum as SAEnum, UniqueConstraint

from app.models.agency import Agency, AgencyStatus, ConnectionType
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.connection_log import ConnectionLog
from app.models.conversation import Conversation, Message
from app.models.evaluation import EvalResult, GoldenQuestion
from app.models.event import DomainEvent
from app.models.executive_brief import ExecutiveBrief
from app.models.llm_provider import LlmProvider
from app.models.llm_route import LlmRoute
from app.models.llm_usage import LlmUsage
from app.models.popular_question import PopularQuestion, PopularQuestionSource
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


def test_connection_log_fk_cascade():
    t = ConnectionLog.__table__
    assert t.name == "connection_logs"
    assert t.c.action.default.arg == "test"
    fk = list(t.c.agency_id.foreign_keys)[0]
    assert fk.column.table.name == "agencies"
    assert fk.ondelete == "CASCADE"
    assert t.c.agency_id.nullable


def test_conversation_metadata_renamed_to_meta():
    t = Conversation.__table__
    assert t.name == "conversations"
    assert t.c.title.default.arg == "สนทนาใหม่"
    assert t.c.title.type.length == 500
    assert "metadata" in t.c
    assert Conversation.meta.property.columns[0].name == "metadata"


def test_message_fk_cascade():
    t = Message.__table__
    assert t.name == "messages"
    fk = list(t.c.conversation_id.foreign_keys)[0]
    assert fk.column.table.name == "conversations"
    assert fk.ondelete == "CASCADE"
    assert not t.c.conversation_id.nullable


def test_golden_question_fk_cascade():
    t = GoldenQuestion.__table__
    assert t.name == "golden_questions"
    fk = list(t.c.agency_id.foreign_keys)[0]
    assert fk.column.table.name == "agencies"
    assert fk.ondelete == "CASCADE"


def test_eval_result_fk_cascade():
    t = EvalResult.__table__
    assert t.name == "eval_results"
    fk = list(t.c.golden_question_id.foreign_keys)[0]
    assert fk.column.table.name == "golden_questions"
    assert fk.ondelete == "CASCADE"


def test_llm_route_fk_restrict():
    t = LlmRoute.__table__
    assert t.name == "llm_routes"
    assert t.c.purpose.unique
    assert t.c.purpose.type.length == 50
    fk = list(t.c.provider_id.foreign_keys)[0]
    assert fk.column.table.name == "llm_providers"
    assert fk.ondelete == "RESTRICT"


def test_popular_question_fk_set_null():
    t = PopularQuestion.__table__
    assert t.name == "popular_questions"
    assert t.c.text_key.unique
    assert t.c.source.default.arg == PopularQuestionSource.manual
    fk = list(t.c.agency_id.foreign_keys)[0]
    assert fk.column.table.name == "agencies"
    assert fk.ondelete == "SET NULL"
    assert t.c.agency_id.nullable


def test_all_15_tables_registered():
    from app import models  # noqa: F401

    expected = {
        "agencies", "audit_logs", "connection_logs", "conversations", "messages",
        "golden_questions", "eval_results", "domain_events", "executive_briefs",
        "llm_providers", "llm_routes", "llm_usage", "popular_questions",
        "rate_limit_counters", "settings",
    }
    assert expected <= set(Base.metadata.tables)
