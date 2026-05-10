"""SQLAlchemy ORM 模型定义"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DocumentORM(Base):
    __tablename__ = "rag_documents"

    doc_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    raw_file_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    file_type: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    error_msg: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str | None] = mapped_column(String(64))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_documents_status", "status"),
        Index("idx_documents_created_by", "created_by"),
        Index("idx_documents_uploaded_at", uploaded_at.desc()),
    )


class ChunkORM(Base):
    __tablename__ = "rag_chunks"

    chunk_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    doc_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    chunk_type: Mapped[str] = mapped_column(String(16), nullable=False)
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    elements: Mapped[dict] = mapped_column(JSONB, nullable=False)
    image_urls: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="[]")
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    group_id: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_chunks_doc_id", "doc_id"),
        Index("idx_chunks_page", "doc_id", "page"),
        Index("idx_chunks_type", "chunk_type"),
        {"sqlite_autoincrement": True},
    )


class QueryLogORM(Base):
    __tablename__ = "rag_query_logs"

    log_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    retrieved_chunks: Mapped[dict | None] = mapped_column(JSONB)
    retrieval_ms: Mapped[int | None] = mapped_column(Integer)
    llm_ms: Mapped[int | None] = mapped_column(Integer)
    total_ms: Mapped[int | None] = mapped_column(Integer)
    token_count: Mapped[int | None] = mapped_column(Integer)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_query_logs_created_at", created_at.desc()),
        Index("idx_query_logs_created_by", "created_by"),
    )
