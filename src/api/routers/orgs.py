"""组织管理路由"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from src.api.auth_utils import decode_access_token
from src.api.schemas.orgs import (
    ChangeRoleRequest,
    CreateInvitationRequest,
    CreateOrgRequest,
    InvitationResponse,
    MemberResponse,
    OrgResponse,
    UpdateOrgRequest,
)

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


@router.post("/orgs/{org_id}/invitations", response_model=InvitationResponse, status_code=201)
async def invite_member(request: Request, org_id: str, body: CreateInvitationRequest):
    user_id = _get_user_id(request)
    pg_store = request.app.state.pg_store

    membership = await pg_store.get_membership(org_id, user_id)
    if membership is None or membership.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可邀请成员")

    target = await pg_store.get_user_by_username(body.username)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    existing_member = await pg_store.get_membership(org_id, target.user_id)
    if existing_member is not None:
        raise HTTPException(status_code=409, detail="该用户已在组织中")

    existing_inv = await pg_store.get_pending_invitation(org_id, target.user_id)
    if existing_inv is not None:
        raise HTTPException(status_code=409, detail="该用户已有待处理的邀请")

    org = await pg_store.get_organization(org_id)
    inv = await pg_store.create_invitation(
        invitation_id=f"inv_{uuid.uuid4().hex[:12]}",
        org_id=org_id,
        inviter_user_id=user_id,
        invitee_user_id=target.user_id,
    )
    return InvitationResponse(
        invitation_id=inv.invitation_id,
        org_id=inv.org_id,
        org_name=org.name if org else "",
        inviter_user_id=inv.inviter_user_id,
        inviter_username="",
        invitee_user_id=inv.invitee_user_id,
        status=inv.status,
        created_at=inv.created_at.isoformat() if inv.created_at else None,
    )


@router.patch("/orgs/{org_id}/members/{target_user_id}", response_model=MemberResponse)
async def change_member_role(request: Request, org_id: str, target_user_id: str, body: ChangeRoleRequest):
    user_id = _get_user_id(request)
    pg_store = request.app.state.pg_store

    membership = await pg_store.get_membership(org_id, user_id)
    if membership is None or membership.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可修改成员角色")

    target_membership = await pg_store.get_membership(org_id, target_user_id)
    if target_membership is None:
        raise HTTPException(status_code=404, detail="该用户不在组织中")

    await pg_store.update_membership_role(target_membership.membership_id, body.role)

    return MemberResponse(
        membership_id=target_membership.membership_id,
        org_id=target_membership.org_id,
        user_id=target_membership.user_id,
        username="",
        display_name=None,
        role=body.role,
        joined_at=target_membership.joined_at,
    )


@router.delete("/orgs/{org_id}/members/me", status_code=200)
async def leave_org(request: Request, org_id: str):
    user_id = _get_user_id(request)
    pg_store = request.app.state.pg_store

    membership = await pg_store.get_membership(org_id, user_id)
    if membership is None:
        raise HTTPException(status_code=404, detail="您不在该组织中")

    if membership.role == "admin":
        admin_count = await pg_store.count_members_by_role(org_id, "admin")
        if admin_count <= 1:
            raise HTTPException(status_code=403, detail="唯一管理员不能退出组织，请先转让管理员角色")

    await pg_store.delete_membership(org_id, user_id)
    return {"detail": "已退出组织"}


@router.delete("/orgs/{org_id}/members/{target_user_id}", status_code=200)
async def remove_member(request: Request, org_id: str, target_user_id: str):
    user_id = _get_user_id(request)
    pg_store = request.app.state.pg_store

    membership = await pg_store.get_membership(org_id, user_id)
    if membership is None or membership.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可移除成员")

    if target_user_id == "me":
        raise HTTPException(status_code=400, detail="请使用 /members/me 端点退出组织")

    if target_user_id == user_id:
        raise HTTPException(status_code=403, detail="管理员不能移除自己，请使用退出流程")

    target_membership = await pg_store.get_membership(org_id, target_user_id)
    if target_membership is None:
        raise HTTPException(status_code=404, detail="该用户不在组织中")

    await pg_store.delete_membership(org_id, target_user_id)
    return {"detail": "已移除成员"}
