"""分块管理 Schema"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChunkListItem(BaseModel):
    """分块列表项"""

    chunk_id: str
    doc_id: str
    chunk_type: str
    page: int
    chunk_index: int
    char_count: int
    full_text: str = Field(description="截断预览，最多 200 字符")
    element_count: int
    group_id: str = ""
    created_at: datetime | None = None


class ChunkListResponse(BaseModel):
    """分块列表响应"""

    total: int
    page: int
    size: int
    items: list[ChunkListItem]


class ChunkDetail(BaseModel):
    """分块详情"""

    chunk_id: str
    doc_id: str
    chunk_type: str
    page: int
    chunk_index: int
    char_count: int
    full_text: str
    elements: list[dict]
    image_urls: list[str] = []
    group_id: str = ""
    created_at: datetime | None = None


class MergeRequest(BaseModel):
    """合并请求"""

    chunk_ids: list[str] = Field(..., min_length=2, description="待合并的 chunk_id 列表，至少 2 个")


class MergeResponse(BaseModel):
    """合并结果"""

    merged_chunk_id: str
    deleted_chunk_ids: list[str]
    char_count: int


class SplitRequest(BaseModel):
    """拆分请求"""

    split_at: int = Field(..., ge=1, description="元素索引：elements[0:split_at] 归 A，elements[split_at:] 归 B")
    link_group: bool = Field(default=False, description="是否将两个子 chunk 关联到同一 group_id")


class SplitChunkInfo(BaseModel):
    """拆分后的分块信息"""

    chunk_id: str
    char_count: int
    element_count: int


class SplitResponse(BaseModel):
    """拆分结果"""

    chunk_a: SplitChunkInfo
    chunk_b: SplitChunkInfo
    deleted_chunk_id: str


class LinkRequest(BaseModel):
    """关联请求"""

    chunk_ids: list[str] = Field(..., min_length=2, description="待关联的 chunk_id 列表，至少 2 个")


class LinkResponse(BaseModel):
    """关联结果"""

    group_id: str
    chunk_ids: list[str]


class UnlinkRequest(BaseModel):
    """取消关联请求"""

    chunk_ids: list[str] = Field(..., min_length=1, description="待取消关联的 chunk_id 列表")


class UnlinkResponse(BaseModel):
    """取消关联结果"""

    unlinked_count: int
