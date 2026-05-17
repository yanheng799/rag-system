"""鉴权中间件测试 — get_current_user 依赖注入"""

from unittest.mock import patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.api.auth_utils import create_access_token
from src.api.deps import get_current_user


def _make_app():
    """创建测试应用，包含受保护端点和公开端点"""
    app = FastAPI()

    @app.get("/protected")
    async def protected_endpoint(user=Depends(get_current_user)):
        return {"user_id": user["user_id"], "org_id": user["org_id"]}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return TestClient(app)


class TestUnauthenticatedAccess:
    """无 token 访问受保护端点"""

    @patch("src.api.deps.settings.auth_enabled", True)
    def test_no_auth_header_returns_401(self):
        client = _make_app()
        resp = client.get("/protected")
        assert resp.status_code == 401

    @patch("src.api.deps.settings.auth_enabled", True)
    def test_invalid_token_returns_401(self):
        client = _make_app()
        resp = client.get("/protected", headers={
            "Authorization": "Bearer invalid.token.here",
        })
        assert resp.status_code == 401

    @patch("src.api.deps.settings.auth_enabled", True)
    def test_expired_token_returns_401(self):
        client = _make_app()
        token = create_access_token("usr_test123", org_id="", expires_hours=-1)
        resp = client.get("/protected", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 401


class TestAuthenticatedAccess:
    """有效 token 访问"""

    @patch("src.api.deps.settings.auth_enabled", True)
    def test_valid_token_returns_200(self):
        client = _make_app()
        token = create_access_token("usr_test123", org_id="org_abc")
        resp = client.get("/protected", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "usr_test123"
        assert data["org_id"] == "org_abc"

    @patch("src.api.deps.settings.auth_enabled", True)
    def test_valid_token_empty_org_id_returns_403(self):
        client = _make_app()
        token = create_access_token("usr_test123", org_id="")
        resp = client.get("/protected", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 403

    @patch("src.api.deps.settings.auth_enabled", True)
    def test_missing_bearer_prefix_returns_401(self):
        client = _make_app()
        token = create_access_token("usr_test123", org_id="org_abc")
        resp = client.get("/protected", headers={
            "Authorization": f"Token {token}",
        })
        assert resp.status_code == 401


class TestAuthDisabled:
    """AUTH_ENABLED=false 时跳过鉴权"""

    @patch("src.api.deps.settings.auth_enabled", False)
    def test_no_token_when_auth_disabled(self):
        client = _make_app()
        resp = client.get("/protected")
        assert resp.status_code == 200

    def test_health_endpoint_always_accessible(self):
        client = _make_app()
        resp = client.get("/health")
        assert resp.status_code == 200
