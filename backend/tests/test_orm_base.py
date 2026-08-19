from app.models.base import Base


def test_base_has_metadata_and_naming_convention():
    assert Base.metadata is not None
    assert "ix" in Base.metadata.naming_convention
