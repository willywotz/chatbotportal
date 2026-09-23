from app.core.base import Base
import app.core.registry  # noqa: F401  (populates Base.metadata)


def test_monitoring_tables_registered():
    tables = set(Base.metadata.tables)
    assert {"agency_check_state", "uptime_bucket", "incidents"} <= tables


def test_uptime_bucket_unique_constraint():
    t = Base.metadata.tables["uptime_bucket"]
    cols = {frozenset(c.columns.keys()) for c in t.constraints if c.__class__.__name__ == "UniqueConstraint"}
    assert frozenset({"agency_id", "granularity", "bucket_start"}) in cols


def test_incident_partial_unique_index():
    t = Base.metadata.tables["incidents"]
    partials = [i for i in t.indexes if i.unique and i.dialect_options["postgresql"].get("where") is not None]
    assert partials, "expected a partial-unique index on incidents"
