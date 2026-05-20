"""backfill_org_id_and_not_null

将存量数据的 org_id 回填为默认组织，并将 org_id 改为 NOT NULL。

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_ORG_ID = "org_default"


def _ensure_default_org(conn):
    """幂等创建默认组织（如不存在）"""
    existing = conn.execute(
        sa.text("SELECT 1 FROM rag_organizations WHERE org_id = :org_id"),
        {"org_id": DEFAULT_ORG_ID},
    ).fetchone()
    if existing is None:
        conn.execute(
            sa.text(
                "INSERT INTO rag_organizations (org_id, name, description, created_by) "
                "VALUES (:org_id, :name, :desc, :created_by)"
            ),
            {
                "org_id": DEFAULT_ORG_ID,
                "name": "default",
                "desc": "默认组织（存量数据）",
                "created_by": "usr_system",
            },
        )


def upgrade() -> None:
    conn = op.get_bind()

    # 1. 创建默认组织（幂等）
    _ensure_default_org(conn)

    # 2. 回填 org_id
    conn.execute(
        sa.text("UPDATE rag_datasets SET org_id = :org_id WHERE org_id IS NULL"),
        {"org_id": DEFAULT_ORG_ID},
    )
    conn.execute(
        sa.text("UPDATE rag_documents SET org_id = :org_id WHERE org_id IS NULL"),
        {"org_id": DEFAULT_ORG_ID},
    )
    conn.execute(
        sa.text("UPDATE rag_query_logs SET org_id = :org_id WHERE org_id IS NULL"),
        {"org_id": DEFAULT_ORG_ID},
    )

    # 3. 改为 NOT NULL（先确保无 null 值）
    op.alter_column("rag_datasets", "org_id", existing_type=sa.String(36), nullable=False)
    op.alter_column("rag_documents", "org_id", existing_type=sa.String(36), nullable=False)
    op.alter_column("rag_query_logs", "org_id", existing_type=sa.String(36), nullable=False)


def downgrade() -> None:
    op.alter_column("rag_query_logs", "org_id", existing_type=sa.String(36), nullable=True)
    op.alter_column("rag_documents", "org_id", existing_type=sa.String(36), nullable=True)
    op.alter_column("rag_datasets", "org_id", existing_type=sa.String(36), nullable=True)
