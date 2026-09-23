"""Fixed-window rate-limit counter: one row per (key, window_start)."""
from sqlalchemy import BigInteger, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RateLimitCounter(Base):
    __tablename__ = "rate_limit_counters"
    __table_args__ = (UniqueConstraint("key", "window_start"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128))
    window_start: Mapped[int] = mapped_column(BigInteger)  # epoch microseconds, window-floored
    count: Mapped[int] = mapped_column(Integer, default=0)
