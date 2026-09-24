"""llm pluggable langchain

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('llm_routes')
    op.drop_table('llm_providers')
    op.create_table(
        'llm_provider',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('model', sa.String(length=200), nullable=False),
        sa.Column('base_url', sa.String(length=500), nullable=True),
        sa.Column('api_key', sa.Text(), nullable=False),
        sa.Column('timeout_seconds', sa.Float(), nullable=False),
        sa.Column('max_retries', sa.Integer(), nullable=False),
        sa.Column('rate_limit_rps', sa.Integer(), nullable=True),
        sa.Column('rate_limit_rpm', sa.Integer(), nullable=True),
        sa.Column('max_queue_size', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_llm_provider')),
        sa.UniqueConstraint('name', name=op.f('uq_llm_provider_name')),
    )
    op.create_table(
        'llm_binding',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('purpose', sa.String(length=50), nullable=False),
        sa.Column('provider_id', sa.UUID(), nullable=False),
        sa.Column('model_override', sa.String(length=200), nullable=True),
        sa.Column('timeout_override', sa.Float(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['provider_id'], ['llm_provider.id'],
                                name=op.f('fk_llm_binding_provider_id_llm_provider'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_llm_binding')),
        sa.UniqueConstraint('purpose', name=op.f('uq_llm_binding_purpose')),
    )


def downgrade() -> None:
    op.drop_table('llm_binding')
    op.drop_table('llm_provider')
    op.create_table(
        'llm_providers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('base_url', sa.String(length=500), nullable=False),
        sa.Column('api_key', sa.Text(), nullable=False),
        sa.Column('auth_header', sa.String(length=100), nullable=False),
        sa.Column('auth_scheme', sa.String(length=50), nullable=False),
        sa.Column('timeout_seconds', sa.Float(), nullable=False),
        sa.Column('request_usage', sa.Boolean(), nullable=False),
        sa.Column('rate_limit_rps', sa.Integer(), nullable=True),
        sa.Column('rate_limit_rpm', sa.Integer(), nullable=True),
        sa.Column('max_queue_size', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_llm_providers')),
        sa.UniqueConstraint('name', name=op.f('uq_llm_providers_name')),
    )
    op.create_table(
        'llm_routes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('purpose', sa.String(length=50), nullable=False),
        sa.Column('provider_id', sa.UUID(), nullable=False),
        sa.Column('model', sa.String(length=200), nullable=False),
        sa.Column('timeout_override', sa.Float(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['provider_id'], ['llm_providers.id'],
                                name=op.f('fk_llm_routes_provider_id_llm_providers'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_llm_routes')),
        sa.UniqueConstraint('purpose', name=op.f('uq_llm_routes_purpose')),
    )
