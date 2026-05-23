"""FastAPI 依赖注入 — 鉴权（JWT + API Key 双重认证）"""

import hashlib

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.api.auth_utils import decode_access_token
from src.config.settings import settings

API_KEY_PREFIX = "rag-"
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict:
    """从 Authorization 头解析 JWT 或 API Key，返回 user_id 和 org_id"""
    if not settings.auth_enabled:
        return {"user_id": "", "org_id": None}

    if credentials is None:
        raise HTTPException(status_code=401, detail="未提供认证令牌")

    token = credentials.credentials

    # API Key 路径：rag- 前缀
    if token.startswith(API_KEY_PREFIX):
        return await _authenticate_api_key(request, token)

    # JWT 路径
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")

    org_id = payload.get("org_id", "")
    if not org_id:
        raise HTTPException(status_code=403, detail="请先创建或加入组织")

    return {"user_id": payload["user_id"], "org_id": org_id}


async def _authenticate_api_key(request: Request, raw_key: str) -> dict:
    """通过 API Key hash 查库认证，返回 user_id 和 org_id"""
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    pg_store = request.app.state.pg_store

    api_key = await pg_store.get_api_key_by_hash(key_hash)
    if api_key is None:
        raise HTTPException(status_code=401, detail="API Key 无效或已撤销")

    return {"user_id": api_key.user_id, "org_id": api_key.org_id}
