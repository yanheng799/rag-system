"""add_datasets_table

Revision ID: 3841a82ebd2e
Revises: 455c49dfeb3d
Create Date: 2026-05-12 10:43:31.806040

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3841a82ebd2e'
down_revision: Union[str, Sequence[str], None] = '455c49dfeb3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 创建数据集表
    op.create_table(
        'rag_datasets',
        sa.Column('dataset_id', sa.String(64), primary_key=True),
        sa.Column('name', sa.String(256), nullable=False, unique=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('created_by', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_datasets_created_at', 'rag_datasets', [sa.text('created_at DESC')])

    # rag_documents 增加数据集关联（可空）
    op.add_column(
        'rag_documents',
        sa.Column('dataset_id', sa.String(64), nullable=True),
    )
    op.create_foreign_key(
        'fk_documents_dataset_id',
        'rag_documents', 'rag_datasets',
        ['dataset_id'], ['dataset_id'],
        ondelete='CASCADE',
    )
    op.create_index('idx_documents_dataset_id', 'rag_documents', ['dataset_id'])


def downgrade() -> None:
    op.drop_index('idx_documents_dataset_id', table_name='rag_documents')
    op.drop_constraint('fk_documents_dataset_id', 'rag_documents', type_='foreignkey')
    op.drop_column('rag_documents', 'dataset_id')
    op.drop_index('idx_datasets_created_at', table_name='rag_datasets')
    op.drop_table('rag_datasets')
