"""The Role literal accepts the three roles and rejects everything else."""
import pytest
from pydantic import ValidationError

from app.features.identity.schemas.user import UserCreate


@pytest.mark.parametrize("role", ["user", "staff", "admin"])
def test_supported_roles_accepted(role):
    assert UserCreate(email="a@x.com", role=role, password="secret123").role == role


@pytest.mark.parametrize("role", ["viewer", "auditor", "agency_owner", "superuser", ""])
def test_unknown_roles_rejected(role):
    with pytest.raises(ValidationError):
        UserCreate(email="a@x.com", role=role)


def test_role_defaults_to_user():
    assert UserCreate(email="a@x.com", password="secret123").role == "user"
