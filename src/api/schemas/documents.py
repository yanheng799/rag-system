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


class IngestRequest(BaseModel):
    doc_ids: list[str] = Field(..., min_length=1, description="待摄入的文档 ID 列表")


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
