"""add_content_hash_to_documents

Revision ID: 68554d36628c
Revises: 74547c9aa4d2
Create Date: 2026-05-10 19:47:25.182237

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '68554d36628c'
down_revision: Union[str, Sequence[str], None] = '74547c9aa4d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('rag_documents', sa.Column('content_hash', sa.String(64), nullable=True))
    op.create_index('idx_documents_content_hash', 'rag_documents', ['content_hash'], unique=True)


def downgrade() -> None:
    op.drop_index('idx_documents_content_hash', table_name='rag_documents')
    op.drop_column('rag_documents', 'content_hash')
