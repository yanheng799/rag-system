"""认证管理路由"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from src.api.auth_utils import create_access_token, decode_access_token, hash_password, verify_password
from src.api.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from src.api.schemas.orgs import SwitchOrgRequest

router = APIRouter(prefix="/api/v1/auth", tags=["认证管理"])


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
