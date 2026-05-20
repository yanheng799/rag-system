"""add_invitations_table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'rag_invitations',
        sa.Column('invitation_id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('rag_organizations.org_id', ondelete='CASCADE'), nullable=False),
        sa.Column('inviter_user_id', sa.String(36), sa.ForeignKey('rag_users.user_id', ondelete='CASCADE'), nullable=False),
        sa.Column('invitee_user_id', sa.String(36), sa.ForeignKey('rag_users.user_id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column('responded_at', sa.DateTime, nullable=True),
    )
    op.create_index('idx_invitations_org_id', 'rag_invitations', ['org_id'])
    op.create_index('idx_invitations_invitee', 'rag_invitations', ['invitee_user_id'])
    op.create_index('idx_invitations_status', 'rag_invitations', ['status'])


def downgrade() -> None:
    op.drop_table('rag_invitations')
