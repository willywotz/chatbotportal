"""Golden questions and per-run evaluation scores for agency answer quality."""

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.agency import Agency
from app.models.base import Base
from app.utils import generate_uuid


class GoldenQuestion(Base):
    __tablename__ = "golden_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False,
    )
    agency: Mapped["Agency"] = relationship(lazy="raise")
    question: Mapped[str] = mapped_column(Text)
    expected_topics: Mapped[list] = mapped_column(MutableList.as_mutable(JSONB), default=list)  # list[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    golden_question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("golden_questions.id", ondelete="CASCADE"), nullable=False,
    )
    golden_question: Mapped["GoldenQuestion"] = relationship(lazy="raise")
    score: Mapped[float] = mapped_column(Float)
    answer: Mapped[str] = mapped_column(Text, default="")
    judge_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
