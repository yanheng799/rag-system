"""核心数据结构定义：ContentElement、ChunkMetadata、MixedChunk、RetrievedChunk"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ContentElement:
    """内容元素：文字或表格"""

    type: str  # "text" | "table"
    content: str  # 文字原文或表格 Markdown 内容
    image_url: Optional[str] = None  # 仅 table 有值，内部 OSS 路径

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "content": self.content,
            "image_url": self.image_url,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ContentElement:
        return cls(
            type=data["type"],
            content=data["content"],
            image_url=data.get("image_url"),
        )


@dataclass
class ChunkMetadata:
    """分块元数据"""

    chunk_id: str  # 格式：{doc_id}_p{page}_c{index}
    chunk_type: str  # "text" | "table" | "mixed"
    source: str  # 原始文件名
    page: int  # 所在页码（Excel 使用 sheet index）
    chunk_index: int  # 该页第几个分块（从 0 起）
    char_count: int  # full_text 字符数
    created_at: str  # 摄入时间，ISO 8601 格式
    doc_id: str  # 所属文档 ID

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "chunk_type": self.chunk_type,
            "source": self.source,
            "page": self.page,
            "chunk_index": self.chunk_index,
            "char_count": self.char_count,
            "created_at": self.created_at,
            "doc_id": self.doc_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ChunkMetadata:
        return cls(
            chunk_id=data["chunk_id"],
            chunk_type=data["chunk_type"],
            source=data["source"],
            page=data["page"],
            chunk_index=data["chunk_index"],
            char_count=data["char_count"],
            created_at=data["created_at"],
            doc_id=data["doc_id"],
        )


@dataclass
class MixedChunk:
    """混合分块：可包含交错的文字和表格元素"""

    metadata: ChunkMetadata
    elements: list[ContentElement] = field(default_factory=list)
    full_text: str = ""
    image_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata.to_dict(),
            "elements": [e.to_dict() for e in self.elements],
            "full_text": self.full_text,
            "image_urls": self.image_urls,
        }


@dataclass
class RetrievedChunk:
    """检索召回的分块结果"""

    metadata: ChunkMetadata
    elements: list[ContentElement] = field(default_factory=list)
    full_text: str = ""
    image_urls: list[str] = field(default_factory=list)
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata.to_dict(),
            "elements": [e.to_dict() for e in self.elements],
            "full_text": self.full_text,
            "image_urls": self.image_urls,
        }
