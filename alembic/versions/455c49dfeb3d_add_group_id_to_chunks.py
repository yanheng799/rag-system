"""add_group_id_to_chunks

Revision ID: 455c49dfeb3d
Revises: 68554d36628c
Create Date: 2026-05-10 20:30:17.648945

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '455c49dfeb3d'
down_revision: Union[str, Sequence[str], None] = '68554d36628c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('rag_chunks', sa.Column('group_id', sa.String(128), server_default='', nullable=False))
    op.create_index('idx_chunks_group_id', 'rag_chunks', ['group_id'])


def downgrade() -> None:
    op.drop_index('idx_chunks_group_id', table_name='rag_chunks')
    op.drop_column('rag_chunks', 'group_id')
