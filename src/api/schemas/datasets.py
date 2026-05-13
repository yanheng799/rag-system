"""数据集接口 Pydantic 模型"""

from datetime import datetime

from pydantic import BaseModel, Field


class DatasetCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str | None = None


class DatasetUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=256)
    description: str | None = None


class DatasetResponse(BaseModel):
    dataset_id: str
    name: str
    description: str | None = None
    doc_count: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DatasetListResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[DatasetResponse]
