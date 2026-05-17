"""JWT 签发/验证 + 密码哈希工具"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from src.config.settings import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: str, org_id: str = "", expires_hours: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=expires_hours or settings.jwt_expire_hours)
    payload = {
        "user_id": user_id,
        "org_id": org_id,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
