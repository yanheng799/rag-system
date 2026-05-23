"""API Key 管理路由：创建、列表、撤销"""

from __future__ import annotations

import hashlib
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.api.deps import get_current_user

router = APIRouter(prefix="/api/v1/api-keys", tags=["API Key"])


class CreateApiKeyRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128, description="Key 名称")
    org_id: str = Field(..., description="绑定的组织 ID")
    expires_at: str | None = Field(default=None, description="过期时间（ISO 8601）")


class ApiKeyResponse(BaseModel):
    key_id: str
    name: str | None
    key_prefix: str
    org_id: str
    created_at: str
    expires_at: str | None
    last_used_at: str | None


class CreateApiKeyResponse(ApiKeyResponse):
    key: str


class RevokeApiKeyResponse(BaseModel):
    revoked: bool


@router.post("", response_model=CreateApiKeyResponse, summary="创建 API Key")
async def create_api_key(request: Request, body: CreateApiKeyRequest, user: dict = Depends(get_current_user)):
    """创建 API Key，明文仅在此响应中返回一次"""
    pg_store = request.app.state.pg_store
    user_id = user["user_id"]

    # 校验用户属于该组织
    membership = await pg_store.get_membership(body.org_id, user_id)
    if membership is None:
        raise HTTPException(status_code=403, detail="您不属于该组织")

    # 生成 key：rag-ak-{32 字节随机 hex}
    raw_key = f"rag-ak-{secrets.token_hex(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:12]  # "rag-ak-xxxxx"
    key_id = f"ak_{uuid.uuid4().hex[:12]}"

    expires_at = body.expires_at

    await pg_store.create_api_key(
        key_id=key_id,
        user_id=user_id,
        org_id=body.org_id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=body.name,
        expires_at=expires_at,
    )

    return CreateApiKeyResponse(
        key_id=key_id,
        name=body.name,
        key=raw_key,
        key_prefix=key_prefix,
        org_id=body.org_id,
        created_at="",
        expires_at=expires_at,
        last_used_at=None,
    )


@router.get("", response_model=list[ApiKeyResponse], summary="列出 API Key")
async def list_api_keys(request: Request, user: dict = Depends(get_current_user)):
    """列出当前用户的所有有效 API Key（不返回明文）"""
    pg_store = request.app.state.pg_store
    keys = await pg_store.list_api_keys(user["user_id"])

    return [
        ApiKeyResponse(
            key_id=k.key_id,
            name=k.name,
            key_prefix=k.key_prefix,
            org_id=k.org_id,
            created_at=k.created_at.isoformat() if k.created_at else "",
            expires_at=k.expires_at.isoformat() if k.expires_at else None,
            last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
        )
        for k in keys
    ]


@router.delete("/{key_id}", response_model=RevokeApiKeyResponse, summary="撤销 API Key")
async def revoke_api_key(request: Request, key_id: str, user: dict = Depends(get_current_user)):
    """撤销指定的 API Key"""
    pg_store = request.app.state.pg_store
    revoked = await pg_store.revoke_api_key(key_id, user["user_id"])
    if not revoked:
        raise HTTPException(status_code=404, detail="API Key 不存在或已撤销")
    return RevokeApiKeyResponse(revoked=True)
