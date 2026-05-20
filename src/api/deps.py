"""FastAPI 依赖注入 — 鉴权"""

from fastapi import HTTPException, Request

from src.api.auth_utils import decode_access_token
from src.config.settings import settings


async def get_current_user(request: Request) -> dict:
    """从 Authorization 头解析 JWT，返回 user_id 和 org_id"""
    if not settings.auth_enabled:
        return {"user_id": "", "org_id": None}

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供认证令牌")

    token = auth[7:]
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")

    org_id = payload.get("org_id", "")
    if not org_id:
        raise HTTPException(status_code=403, detail="请先创建或加入组织")

    return {"user_id": payload["user_id"], "org_id": org_id}
