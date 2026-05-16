"""add chunk_options to documents

Revision ID: a1b2c3d4e5f6
Revises: 3841a82ebd2e
Create Date: 2026-05-16
"""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "3841a82ebd2e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("rag_documents", sa.Column("chunk_options", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("rag_documents", "chunk_options")
