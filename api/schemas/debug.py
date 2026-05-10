"""调试检索接口 Pydantic 模型"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class RetrieveRequest(BaseModel):
    question: str
    top_k: int = Field(default=10, ge=1, le=50)
    search_mode: Literal["vector"] = "vector"  # Phase 1 仅支持 vector
    show_prompt: bool = False


class DebugChunkMetadata(BaseModel):
    chunk_id: str
    chunk_type: str
    source: str
    page: int
    pages: list[int] = []
    chunk_index: int
    char_count: int
    created_at: str
    doc_id: str


class DebugChunkScores(BaseModel):
    vector_score: float


class DebugChunk(BaseModel):
    rank: int
    metadata: DebugChunkMetadata
    full_text: str
    scores: DebugChunkScores
    image_urls: list[str] = []


class RetrieveResponse(BaseModel):
    question: str
    search_mode: str
    total_retrieved: int
    retrieval_ms: int
    chunks: list[DebugChunk]
    prompt: Optional[str] = None
