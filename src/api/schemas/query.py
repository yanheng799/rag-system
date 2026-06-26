"""查询接口 Pydantic 模型"""

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str
    top_k: int = Field(default=10, ge=1, le=20)
    dataset_ids: list[str] | None = None
    doc_ids: list[str] | None = None
    doc_names: list[str] | None = None
    show_rewritten: bool = Field(default=False, description="是否返回改写后的子查询")
    use_reranker: bool = Field(default=True, description="是否启用 Reranker 重排序")
    rerank_top_n: int = Field(default=5, ge=1, le=50, description="Reranker 输出数量")


class ElementSchema(BaseModel):
    type: str
    content: str
    image_url: str | None = None


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
    rewritten_queries: list[str] | None = None
