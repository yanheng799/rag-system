"""add_org_id_to_business_tables

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('rag_datasets', sa.Column('org_id', sa.String(36), nullable=True))
    op.add_column('rag_documents', sa.Column('org_id', sa.String(36), nullable=True))
    op.add_column('rag_query_logs', sa.Column('org_id', sa.String(36), nullable=True))
    op.create_index('idx_datasets_org_id', 'rag_datasets', ['org_id'])
    op.create_index('idx_documents_org_id', 'rag_documents', ['org_id'])


def downgrade() -> None:
    op.drop_index('idx_documents_org_id', table_name='rag_documents')
    op.drop_index('idx_datasets_org_id', table_name='rag_datasets')
    op.drop_column('rag_query_logs', 'org_id')
    op.drop_column('rag_documents', 'org_id')
    op.drop_column('rag_datasets', 'org_id')
