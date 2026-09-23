"""drop agencies.conformance_report

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("agencies", "conformance_report")


def downgrade() -> None:
    op.add_column(
        "agencies",
        sa.Column(
            "conformance_report",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
