"""self-hosted OIDC provider: users, signing keys, oauth artifacts

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=True),
        sa.Column('role', sa.Enum('user', 'staff', 'admin', name='userrole', native_enum=False, length=20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
        sa.UniqueConstraint('email', name=op.f('uq_users_email')),
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    op.create_table(
        'signing_keys',
        sa.Column('kid', sa.String(length=64), nullable=False),
        sa.Column('private_pem', sa.Text(), nullable=False),
        sa.Column('public_jwk', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('kid', name=op.f('pk_signing_keys')),
    )

    op.create_table(
        'oauth_auth_codes',
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('client_id', sa.String(length=255), nullable=False),
        sa.Column('redirect_uri', sa.String(length=1000), nullable=False),
        sa.Column('code_challenge', sa.String(length=255), nullable=False),
        sa.Column('scope', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('code_hash', name=op.f('pk_oauth_auth_codes')),
    )

    op.create_table(
        'oauth_refresh_tokens',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('client_id', sa.String(length=255), nullable=False),
        sa.Column('scope', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_oauth_refresh_tokens')),
        sa.UniqueConstraint('token_hash', name=op.f('uq_oauth_refresh_tokens_token_hash')),
    )
    op.create_index(op.f('ix_oauth_refresh_tokens_token_hash'), 'oauth_refresh_tokens', ['token_hash'], unique=True)
    op.create_index(op.f('ix_oauth_refresh_tokens_user_id'), 'oauth_refresh_tokens', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_oauth_refresh_tokens_user_id'), table_name='oauth_refresh_tokens')
    op.drop_index(op.f('ix_oauth_refresh_tokens_token_hash'), table_name='oauth_refresh_tokens')
    op.drop_table('oauth_refresh_tokens')
    op.drop_table('oauth_auth_codes')
    op.drop_table('signing_keys')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
