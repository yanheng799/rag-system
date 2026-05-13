"""API 请求/响应 Pydantic 模型"""

from pydantic import BaseModel


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
