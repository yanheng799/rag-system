"""数据集接口 Pydantic 模型"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DatasetCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None


class DatasetUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=256)
    description: Optional[str] = None


class DatasetResponse(BaseModel):
    dataset_id: str
    name: str
    description: Optional[str] = None
    doc_count: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DatasetListResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[DatasetResponse]
