from sqlalchemy import Enum as SAEnum

from app.models.agency import Agency, AgencyStatus, ConnectionType
from app.models.base import Base


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
