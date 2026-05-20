"""组织管理路由"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from src.api.auth_utils import decode_access_token
from src.api.schemas.orgs import CreateOrgRequest, MemberResponse, OrgResponse, UpdateOrgRequest

router = APIRouter(prefix="/api/v1", tags=["组织管理"])


def _get_user_id(request: Request) -> str:
    """从请求头提取 JWT 并返回 user_id（不校验 org_id）"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供认证令牌")
    token = auth[7:]
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    return payload["user_id"]


@router.post("/orgs", response_model=OrgResponse, status_code=201)
async def create_org(request: Request, body: CreateOrgRequest):
    user_id = _get_user_id(request)
    pg_store = request.app.state.pg_store

    existing = await pg_store.get_organization_by_name(body.name)
    if existing is not None:
        raise HTTPException(status_code=409, detail="组织名称已被占用")

    org_id = f"org_{uuid.uuid4().hex[:12]}"
    org = await pg_store.create_organization(
        org_id=org_id,
        name=body.name,
        description=body.description,
        created_by=user_id,
    )
    await pg_store.create_membership(
        membership_id=f"mem_{uuid.uuid4().hex[:12]}",
        org_id=org_id,
        user_id=user_id,
        role="admin",
    )
    return OrgResponse(
        org_id=org.org_id,
        name=org.name,
        description=org.description,
        created_by=org.created_by,
        role="admin",
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


@router.get("/orgs", response_model=list[OrgResponse])
async def list_my_orgs(request: Request):
    user_id = _get_user_id(request)
    pg_store = request.app.state.pg_store

    memberships = await pg_store.list_memberships_by_user(user_id)
    return [
        OrgResponse(
            org_id=m.org_id,
            name=m.org_name,
            description=None,
            created_by="",
            role=m.role,
            joined_at=m.joined_at,
        )
        for m in memberships
    ]


@router.get("/orgs/{org_id}", response_model=OrgResponse)
async def get_org(request: Request, org_id: str):
    user_id = _get_user_id(request)
    pg_store = request.app.state.pg_store

    membership = await pg_store.get_membership(org_id, user_id)
    if membership is None:
        raise HTTPException(status_code=403, detail="您不是该组织的成员")

    org = await pg_store.get_organization(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="组织不存在")

    return OrgResponse(
        org_id=org.org_id,
        name=org.name,
        description=org.description,
        created_by=org.created_by,
        role=membership.role,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


@router.patch("/orgs/{org_id}", response_model=OrgResponse)
async def update_org(request: Request, org_id: str, body: UpdateOrgRequest):
    user_id = _get_user_id(request)
    pg_store = request.app.state.pg_store

    membership = await pg_store.get_membership(org_id, user_id)
    if membership is None:
        raise HTTPException(status_code=403, detail="您不是该组织的成员")
    if membership.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可修改组织设置")

    if body.name is not None:
        existing = await pg_store.get_organization_by_name(body.name)
        if existing is not None and existing.org_id != org_id:
            raise HTTPException(status_code=409, detail="组织名称已被占用")

    org = await pg_store.update_organization(
        org_id=org_id,
        name=body.name,
        description=body.description,
    )
    if org is None:
        raise HTTPException(status_code=404, detail="组织不存在")

    return OrgResponse(
        org_id=org.org_id,
        name=org.name,
        description=org.description,
        created_by=org.created_by,
        role=membership.role,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


@router.get("/orgs/{org_id}/members", response_model=list[MemberResponse])
async def list_members(request: Request, org_id: str):
    user_id = _get_user_id(request)
    pg_store = request.app.state.pg_store

    membership = await pg_store.get_membership(org_id, user_id)
    if membership is None:
        raise HTTPException(status_code=403, detail="您不是该组织的成员")

    members = await pg_store.list_members_by_org(org_id)
    return [
        MemberResponse(
            membership_id=m.membership_id,
            org_id=m.org_id,
            user_id=m.user_id,
            username=m.username,
            display_name=m.display_name,
            role=m.role,
            joined_at=m.joined_at,
        )
        for m in members
    ]
