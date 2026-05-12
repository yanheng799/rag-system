"""API 请求/响应 Pydantic 模型"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    dataset_id: Optional[str] = None
    status: str
    uploaded_at: str


class DocumentStatusResponse(BaseModel):
    doc_id: str
    filename: str
    status: str  # pending | processing | done | failed
    error_msg: Optional[str] = None
    uploaded_at: Optional[str] = None
    updated_at: Optional[str] = None
