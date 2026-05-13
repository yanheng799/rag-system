"""查询接口 Pydantic 模型"""

from typing import Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str
    top_k: int = Field(default=5, ge=1, le=20)
    dataset_ids: Optional[list[str]] = None
    doc_ids: Optional[list[str]] = None
    doc_names: Optional[list[str]] = None


class ElementSchema(BaseModel):
    type: str
    content: str
    image_url: Optional[str] = None


class ChunkMetadataSchema(BaseModel):
    chunk_id: str
    chunk_type: str
    filename: str
    page: int
    chunk_index: int
    char_count: int
    created_at: str
    doc_id: str
    score: float


class SourceSchema(BaseModel):
    metadata: ChunkMetadataSchema
    elements: list[ElementSchema]


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceSchema]
    total_ms: int
