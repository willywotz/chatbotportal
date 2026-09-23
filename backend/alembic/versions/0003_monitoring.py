"""monitoring uptime tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["agency_id"], ["agencies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_incident_open_per_agency", "incidents", ["agency_id"],
        unique=True, postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.create_table(
        "uptime_bucket",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("granularity", sa.String(length=8), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_checks", sa.Integer(), nullable=False),
        sa.Column("ok_checks", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["agency_id"], ["agencies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agency_id", "granularity", "bucket_start", name="uq_uptime_bucket_grain"),
    )
    op.create_table(
        "agency_check_state",
        sa.Column("agency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=8), nullable=False),
        sa.Column("last_latency_ms", sa.Integer(), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("current_incident_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["agency_id"], ["agencies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["current_incident_id"], ["incidents.id"],
                                ondelete="SET NULL", use_alter=True, name="fk_check_state_incident"),
        sa.PrimaryKeyConstraint("agency_id"),
    )
    op.create_index("ix_check_state_next_check_at", "agency_check_state", ["next_check_at"])


def downgrade() -> None:
    op.drop_index("ix_check_state_next_check_at", table_name="agency_check_state")
    op.drop_table("agency_check_state")
    op.drop_table("uptime_bucket")
    op.drop_index("uq_incident_open_per_agency", table_name="incidents")
    op.drop_table("incidents")
