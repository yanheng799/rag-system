"""文档记录数据结构"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class UserRecord:
    """用户记录"""

    user_id: str
    username: str
    display_name: str | None = None
    created_at: datetime | None = None
    # 内部使用，不暴露到 API
    _password_hash: str = field(default="", repr=False)


@dataclass
class DocumentRecord:
    """文档管理记录"""

    doc_id: str
    filename: str
    raw_file_url: str
    content_hash: str | None = None
    dataset_id: str | None = None
    org_id: str | None = None
    file_size: int | None = None
    file_type: str | None = None  # pdf | docx | xlsx
    status: str = "pending"  # pending | processing | done | failed
    error_msg: str | None = None
    retry_count: int = 0
    created_by: str | None = None
    chunk_count: int = 0
    chunk_options: dict | None = None
    uploaded_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class DatasetRecord:
    """数据集记录"""

    dataset_id: str
    name: str
    description: str | None = None
    org_id: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class ChunkRecord:
    """分块记录（PostgreSQL chunks 表对应）"""

    chunk_id: str  # 格式：{doc_id}_p{page}_c{index}
    doc_id: str
    chunk_type: str  # text | table | mixed
    full_text: str
    elements: list[dict]  # ContentElement 序列化列表
    image_urls: list[str]
    page: int
    chunk_index: int
    char_count: int
    group_id: str = ""
    created_at: datetime | None = None


@dataclass
class OrganizationRecord:
    """组织记录"""

    org_id: str
    name: str
    description: str | None = None
    created_by: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class MembershipRecord:
    """成员关系记录"""

    membership_id: str
    org_id: str
    user_id: str
    role: str = "member"  # admin | member
    org_name: str = ""
    username: str = ""
    display_name: str | None = None
    joined_at: datetime | None = None


@dataclass
class InvitationRecord:
    """邀请记录"""

    invitation_id: str
    org_id: str
    inviter_user_id: str
    invitee_user_id: str
    status: str = "pending"  # pending | accepted | rejected | expired
    org_name: str = ""
    inviter_username: str = ""
    invitee_username: str = ""
    created_at: datetime | None = None
    responded_at: datetime | None = None


@dataclass
class QueryLogRecord:
    """查询日志记录"""

    log_id: str
    question: str
    answer: str | None = None
    retrieved_chunks: list[dict] | None = None
    retrieval_ms: int | None = None
    llm_ms: int | None = None
    total_ms: int | None = None
    token_count: int | None = None
    cache_hit: bool = False
    org_id: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None
