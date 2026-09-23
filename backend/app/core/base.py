from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

_NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """`eager_defaults=True`: UPDATE statements fetch server-side
    `onupdate`/`server_default` columns (e.g. `updated_at`) via RETURNING
    immediately, instead of leaving them expired for a later lazy SELECT
    (which fails outside a greenlet, e.g. during sync Pydantic serialization
    right after a flush)."""

    metadata = MetaData(naming_convention=_NAMING)
    __mapper_args__ = {"eager_defaults": True}
