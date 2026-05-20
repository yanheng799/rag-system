"""组织与成员管理请求/响应 Schema"""

from datetime import datetime

from pydantic import BaseModel, Field


class CreateOrgRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str | None = Field(None, max_length=1024)


class UpdateOrgRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=256)
    description: str | None = Field(None, max_length=1024)


class OrgResponse(BaseModel):
    org_id: str
    name: str
    description: str | None = None
    created_by: str
    role: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MemberResponse(BaseModel):
    membership_id: str
    org_id: str
    user_id: str
    username: str
    display_name: str | None = None
    role: str
    joined_at: datetime | None = None


class SwitchOrgRequest(BaseModel):
    org_id: str = Field(..., min_length=1)
