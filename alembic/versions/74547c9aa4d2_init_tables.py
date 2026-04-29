"""init tables

Revision ID: 74547c9aa4d2
Revises:
Create Date: 2026-04-29 00:36:46.188450

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '74547c9aa4d2'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('rag_documents',
        sa.Column('doc_id', sa.String(length=64), nullable=False),
        sa.Column('filename', sa.String(length=512), nullable=False),
        sa.Column('raw_file_url', sa.String(length=1024), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('file_type', sa.String(length=16), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('error_msg', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_by', sa.String(length=64), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('doc_id')
    )
    op.create_index('idx_rag_docs_status', 'rag_documents', ['status'], unique=False)
    op.create_index('idx_rag_docs_created_by', 'rag_documents', ['created_by'], unique=False)
    op.create_index('idx_rag_docs_uploaded_at', 'rag_documents', [sa.literal_column('uploaded_at DESC')], unique=False)

    op.create_table('rag_chunks',
        sa.Column('chunk_id', sa.String(length=128), nullable=False),
        sa.Column('doc_id', sa.String(length=64), nullable=False),
        sa.Column('chunk_type', sa.String(length=16), nullable=False),
        sa.Column('full_text', sa.Text(), nullable=False),
        sa.Column('elements', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('image_urls', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('page', sa.Integer(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('char_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('chunk_id'),
        sa.ForeignKeyConstraint(['doc_id'], ['rag_documents.doc_id'], ondelete='CASCADE'),
    )
    op.create_index('idx_rag_chunks_doc_id', 'rag_chunks', ['doc_id'], unique=False)
    op.create_index('idx_rag_chunks_page', 'rag_chunks', ['doc_id', 'page'], unique=False)
    op.create_index('idx_rag_chunks_type', 'rag_chunks', ['chunk_type'], unique=False)

    op.create_table('rag_query_logs',
        sa.Column('log_id', sa.String(length=64), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=True),
        sa.Column('retrieved_chunks', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('retrieval_ms', sa.Integer(), nullable=True),
        sa.Column('llm_ms', sa.Integer(), nullable=True),
        sa.Column('total_ms', sa.Integer(), nullable=True),
        sa.Column('token_count', sa.Integer(), nullable=True),
        sa.Column('cache_hit', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_by', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('log_id')
    )
    op.create_index('idx_rag_qlogs_created_at', 'rag_query_logs', [sa.literal_column('created_at DESC')], unique=False)
    op.create_index('idx_rag_qlogs_created_by', 'rag_query_logs', ['created_by'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_rag_qlogs_created_by', table_name='rag_query_logs')
    op.drop_index('idx_rag_qlogs_created_at', table_name='rag_query_logs')
    op.drop_table('rag_query_logs')

    op.drop_index('idx_rag_chunks_type', table_name='rag_chunks')
    op.drop_index('idx_rag_chunks_page', table_name='rag_chunks')
    op.drop_index('idx_rag_chunks_doc_id', table_name='rag_chunks')
    op.drop_table('rag_chunks')

    op.drop_index('idx_rag_docs_uploaded_at', table_name='rag_documents')
    op.drop_index('idx_rag_docs_created_by', table_name='rag_documents')
    op.drop_index('idx_rag_docs_status', table_name='rag_documents')
    op.drop_table('rag_documents')
