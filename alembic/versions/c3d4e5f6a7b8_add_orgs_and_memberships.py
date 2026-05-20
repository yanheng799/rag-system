"""add_orgs_and_memberships

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'rag_organizations',
        sa.Column('org_id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(256), nullable=False, unique=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('created_by', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_orgs_name', 'rag_organizations', ['name'])

    op.create_table(
        'rag_memberships',
        sa.Column('membership_id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('rag_organizations.org_id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('rag_users.user_id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(16), nullable=False, server_default='member'),
        sa.Column('joined_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_memberships_org_id', 'rag_memberships', ['org_id'])
    op.create_index('idx_memberships_user_id', 'rag_memberships', ['user_id'])
    op.create_unique_constraint('uq_memberships_org_user', 'rag_memberships', ['org_id', 'user_id'])


def downgrade() -> None:
    op.drop_table('rag_memberships')
    op.drop_table('rag_organizations')
