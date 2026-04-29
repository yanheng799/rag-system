"""调试检索接口 Pydantic 模型"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class RetrieveRequest(BaseModel):
    question: str
    top_k: int = Field(default=10, ge=1, le=50)
    search_mode: Literal["vector"] = "vector"  # Phase 1 仅支持 vector
    show_prompt: bool = False


class DebugChunkScores(BaseModel):
    vector_score: Optional[float] = None


class DebugChunk(BaseModel):
    rank: int
    metadata: dict
    scores: DebugChunkScores
    elements: list[dict]


class RetrieveResponse(BaseModel):
    question: str
    search_mode: str
    total_retrieved: int
    retrieval_ms: int
    chunks: list[DebugChunk]
    prompt: Optional[str] = None
