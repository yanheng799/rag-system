"""认证管理路由"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request

from src.api.auth_utils import create_access_token, decode_access_token, hash_password, verify_password
from src.api.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from src.api.schemas.orgs import InvitationResponse, SwitchOrgRequest

router = APIRouter(prefix="/api/v1/auth", tags=["认证管理"])

INVITATION_TTL = timedelta(days=7)


def _is_invitation_expired(created_at) -> bool:
    """邀请是否超过有效期（默认 7 天）。

    DB 经 asyncpg 返回 offset-aware datetime，而历史代码用 offset-naive 的
    datetime.utcnow() 与之相减会抛 TypeError，故统一以 aware UTC 比较；
    若 created_at 为 naive（如部分测试夹具），视为 UTC。
    """
    if created_at is None:
        return False
    now = datetime.now(UTC)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return now - created_at > INVITATION_TTL


def _get_token(request: Request) -> dict:
    """从请求头提取并验证 JWT token"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供认证令牌")
    token = auth[7:]
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    return payload


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(request: Request, body: RegisterRequest):
    pg_store = request.app.state.pg_store

    existing = await pg_store.get_user_by_username(body.username)
    if existing is not None:
        raise HTTPException(status_code=409, detail="用户名已被占用")

    pw_hash = hash_password(body.password)
    display_name = body.display_name or body.username
    user = await pg_store.create_user(
        user_id=f"usr_{uuid.uuid4().hex[:12]}",
        username=body.username,
        password_hash=pw_hash,
        display_name=display_name,
    )
    return UserResponse(
        user_id=user.user_id,
        username=user.username,
        display_name=user.display_name,
        created_at=user.created_at,
    )


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, body: LoginRequest):
    pg_store = request.app.state.pg_store

    user = await pg_store.get_user_by_username(body.username)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not verify_password(body.password, user._password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token(user.user_id, org_id="")
    return TokenResponse(access_token=token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: Request):
    payload = _get_token(request)
    token = create_access_token(payload["user_id"], org_id=payload.get("org_id", ""))
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def get_me(request: Request):
    payload = _get_token(request)
    pg_store = request.app.state.pg_store

    user = await pg_store.get_user_by_id(payload["user_id"])
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")

    memberships = await pg_store.get_user_memberships(user.user_id)
    organizations = [
        {"org_id": m.org_id, "org_name": m.org_name, "role": m.role}
        for m in memberships
    ]

    return UserResponse(
        user_id=user.user_id,
        username=user.username,
        display_name=user.display_name,
        created_at=user.created_at,
        organizations=organizations,
    )


@router.post("/switch-org", response_model=TokenResponse)
async def switch_org(request: Request, body: SwitchOrgRequest):
    payload = _get_token(request)
    user_id = payload["user_id"]
    pg_store = request.app.state.pg_store

    membership = await pg_store.get_membership(body.org_id, user_id)
    if membership is None:
        raise HTTPException(status_code=403, detail="您不是该组织的成员")

    token = create_access_token(user_id, org_id=body.org_id)
    return TokenResponse(access_token=token)


@router.get("/invitations", response_model=list[InvitationResponse])
async def list_invitations(request: Request):
    payload = _get_token(request)
    user_id = payload["user_id"]
    pg_store = request.app.state.pg_store

    invitations = await pg_store.list_invitations_by_user(user_id)

    result = []
    for inv in invitations:
        expired = False
        status = inv.status
        if inv.status == "pending" and _is_invitation_expired(inv.created_at):
            status = "expired"
            expired = True
        result.append(InvitationResponse(
            invitation_id=inv.invitation_id,
            org_id=inv.org_id,
            org_name=inv.org_name,
            inviter_user_id=inv.inviter_user_id,
            inviter_username=inv.inviter_username,
            invitee_user_id=inv.invitee_user_id,
            status=status,
            created_at=inv.created_at.isoformat() if inv.created_at else None,
            responded_at=inv.responded_at.isoformat() if inv.responded_at else None,
            expired=expired,
        ))
    return result


@router.post("/invitations/{invitation_id}/accept", status_code=200)
async def accept_invitation(request: Request, invitation_id: str):
    payload = _get_token(request)
    user_id = payload["user_id"]
    pg_store = request.app.state.pg_store

    inv = await pg_store.get_invitation(invitation_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="邀请不存在")
    if inv.invitee_user_id != user_id:
        raise HTTPException(status_code=403, detail="这不是发给您的邀请")
    if inv.status != "pending":
        raise HTTPException(status_code=410, detail="邀请已失效")
    if _is_invitation_expired(inv.created_at):
        raise HTTPException(status_code=410, detail="邀请已过期")

    import uuid

    await pg_store.create_membership(
        membership_id=f"mem_{uuid.uuid4().hex[:12]}",
        org_id=inv.org_id,
        user_id=user_id,
        role="member",
    )
    await pg_store.update_invitation_status(invitation_id, "accepted")
    return {"detail": "已加入组织"}


@router.post("/invitations/{invitation_id}/reject", status_code=200)
async def reject_invitation(request: Request, invitation_id: str):
    payload = _get_token(request)
    user_id = payload["user_id"]
    pg_store = request.app.state.pg_store

    inv = await pg_store.get_invitation(invitation_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="邀请不存在")
    if inv.invitee_user_id != user_id:
        raise HTTPException(status_code=403, detail="这不是发给您的邀请")
    if inv.status != "pending":
        raise HTTPException(status_code=410, detail="邀请已失效")
    if _is_invitation_expired(inv.created_at):
        raise HTTPException(status_code=410, detail="邀请已过期")

    await pg_store.update_invitation_status(invitation_id, "rejected")
    return {"detail": "已拒绝邀请"}
