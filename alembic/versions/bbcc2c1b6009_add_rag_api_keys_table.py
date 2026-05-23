"""add rag_api_keys table

Revision ID: bbcc2c1b6009
Revises: f6a7b8c9d0e1
Create Date: 2026-05-23 16:33:24.211044

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'bbcc2c1b6009'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('rag_api_keys',
        sa.Column('key_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('org_id', sa.String(length=36), nullable=False),
        sa.Column('key_hash', sa.String(length=64), nullable=False),
        sa.Column('key_prefix', sa.String(length=12), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['rag_organizations.org_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['rag_users.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('key_id'),
    )
    op.create_index('idx_api_keys_key_hash', 'rag_api_keys', ['key_hash'], unique=False)
    op.create_index('idx_api_keys_user_id', 'rag_api_keys', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_api_keys_user_id', table_name='rag_api_keys')
    op.drop_index('idx_api_keys_key_hash', table_name='rag_api_keys')
    op.drop_table('rag_api_keys')
