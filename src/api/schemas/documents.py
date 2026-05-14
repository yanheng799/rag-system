"""API 请求/响应 Pydantic 模型"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    dataset_id: str | None = None
    status: str
    uploaded_at: str


class DocumentStatusResponse(BaseModel):
    doc_id: str
    filename: str
    status: str  # pending | processing | done | failed
    error_msg: str | None = None
    uploaded_at: str | None = None
    updated_at: str | None = None


class ChunkOptions(BaseModel):
    strategy: str | None = Field(default=None, description="分块策略: paragraph / heading / fixed_size / page")
    max_size: int | None = Field(default=None, description="最大分块字符数")
    min_size: int | None = Field(default=None, description="最小分块字符数（低于此值合并）")
    overlap: int | None = Field(default=None, description="固定大小策略的 overlap 字符数")
    vertical_gap: float | None = Field(default=None, description="段落策略的垂直间距阈值(px)")


class IngestRequest(BaseModel):
    doc_ids: list[str] = Field(..., min_length=1, description="待摄入的文档 ID 列表")
    chunk_options: ChunkOptions | None = Field(default=None, description="分块参数（不传则使用默认策略）")


class IngestResult(BaseModel):
    doc_id: str
    filename: str
    status: str
    error_msg: str | None = None


class IngestResponse(BaseModel):
    results: list[IngestResult]


class DocumentListItem(BaseModel):
    doc_id: str
    filename: str
    status: str
    error_msg: str | None = None
    uploaded_at: str | None = None
    updated_at: str | None = None


class DocumentListResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[DocumentListItem]
