"""文档记录数据结构"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class DocumentRecord:
    """文档管理记录"""

    doc_id: str
    filename: str
    raw_file_url: str
    content_hash: Optional[str] = None
    dataset_id: Optional[str] = None
    file_size: Optional[int] = None
    file_type: Optional[str] = None  # pdf | docx | xlsx
    status: str = "pending"  # pending | processing | done | failed
    error_msg: Optional[str] = None
    retry_count: int = 0
    created_by: Optional[str] = None
    uploaded_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class DatasetRecord:
    """数据集记录"""

    dataset_id: str
    name: str
    description: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class ChunkRecord:
    """分块记录（PostgreSQL chunks 表对应）"""

    chunk_id: str  # 格式：{doc_id}_p{page}_c{index}
    doc_id: str
    chunk_type: str  # text | table | mixed
    full_text: str
    elements: list[dict]  # ContentElement 序列化列表
    image_urls: list[str]
    page: int
    chunk_index: int
    char_count: int
    group_id: str = ""
    created_at: Optional[datetime] = None


@dataclass
class QueryLogRecord:
    """查询日志记录"""

    log_id: str
    question: str
    answer: Optional[str] = None
    retrieved_chunks: Optional[list[dict]] = None
    retrieval_ms: Optional[int] = None
    llm_ms: Optional[int] = None
    total_ms: Optional[int] = None
    token_count: Optional[int] = None
    cache_hit: bool = False
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
