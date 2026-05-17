"""用户注册、登录与 JWT 签发测试"""

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.auth import router


class _FakePgStore:
    """模拟 PgStore 的用户方法"""

    def __init__(self):
        self._users = {}  # username -> {user_id, username, password_hash, display_name}

    async def create_user(self, user_id: str, username: str, password_hash: str, display_name: str):
        from src.models.documents import UserRecord

        self._users[username] = {
            "user_id": user_id,
            "username": username,
            "password_hash": password_hash,
            "display_name": display_name,
        }
        return UserRecord(
            user_id=user_id,
            username=username,
            display_name=display_name,
            created_at=None,
        )

    async def get_user_by_username(self, username: str):
        from src.models.documents import UserRecord

        data = self._users.get(username)
        if not data:
            return None
        rec = UserRecord(
            user_id=data["user_id"],
            username=data["username"],
            display_name=data["display_name"],
            created_at=None,
        )
        rec._password_hash = data["password_hash"]
        return rec

    async def get_user_by_id(self, user_id: str):
        from src.models.documents import UserRecord

        for data in self._users.values():
            if data["user_id"] == user_id:
                rec = UserRecord(
                    user_id=data["user_id"],
                    username=data["username"],
                    display_name=data["display_name"],
                    created_at=None,
                )
                rec._password_hash = data["password_hash"]
                return rec
        return None

    async def get_user_memberships(self, user_id: str):
        return []


def _make_app():
    app = FastAPI()
    app.state.pg_store = _FakePgStore()
    app.include_router(router)
    return app, TestClient(app)


class TestRegister:
    """注册端点测试"""

    def test_register_success(self):
        app, client = _make_app()
        resp = client.post("/api/v1/auth/register", json={
            "username": "alice",
            "password": "secret123",
            "display_name": "Alice",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "alice"
        assert data["display_name"] == "Alice"
        assert "user_id" in data

    def test_register_duplicate_username(self):
        app, client = _make_app()
        client.post("/api/v1/auth/register", json={
            "username": "bob",
            "password": "secret123",
        })
        resp = client.post("/api/v1/auth/register", json={
            "username": "bob",
            "password": "other456",
        })
        assert resp.status_code == 409

    def test_register_username_too_short(self):
        app, client = _make_app()
        resp = client.post("/api/v1/auth/register", json={
            "username": "ab",
            "password": "secret123",
        })
        assert resp.status_code == 422

    def test_register_password_too_short(self):
        app, client = _make_app()
        resp = client.post("/api/v1/auth/register", json={
            "username": "charlie",
            "password": "short",
        })
        assert resp.status_code == 422


class TestLogin:
    """登录端点测试"""

    def _register_and_login(self, client, username="testuser", password="secret123"):
        client.post("/api/v1/auth/register", json={
            "username": username,
            "password": password,
        })
        return client.post("/api/v1/auth/login", json={
            "username": username,
            "password": password,
        })

    def test_login_success(self):
        app, client = _make_app()
        resp = self._register_and_login(client)
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self):
        app, client = _make_app()
        client.post("/api/v1/auth/register", json={
            "username": "dave",
            "password": "secret123",
        })
        resp = client.post("/api/v1/auth/login", json={
            "username": "dave",
            "password": "wrongpass",
        })
        assert resp.status_code == 401

    def test_login_user_not_found(self):
        app, client = _make_app()
        resp = client.post("/api/v1/auth/login", json={
            "username": "nonexistent",
            "password": "secret123",
        })
        assert resp.status_code == 401


class TestRefresh:
    """Token 刷新测试"""

    def test_refresh_token(self):
        app, client = _make_app()
        client.post("/api/v1/auth/register", json={
            "username": "eve",
            "password": "secret123",
        })
        login_resp = client.post("/api/v1/auth/login", json={
            "username": "eve",
            "password": "secret123",
        })
        token = login_resp.json()["access_token"]

        resp = client.post("/api/v1/auth/refresh", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_refresh_invalid_token(self):
        app, client = _make_app()
        resp = client.post("/api/v1/auth/refresh", headers={
            "Authorization": "Bearer invalid.token.here",
        })
        assert resp.status_code == 401


class TestMe:
    """当前用户信息测试"""

    def test_me_authenticated(self):
        app, client = _make_app()
        client.post("/api/v1/auth/register", json={
            "username": "frank",
            "password": "secret123",
        })
        login_resp = client.post("/api/v1/auth/login", json={
            "username": "frank",
            "password": "secret123",
        })
        token = login_resp.json()["access_token"]

        resp = client.get("/api/v1/auth/me", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "frank"
        assert "organizations" in data

    def test_me_unauthenticated(self):
        app, client = _make_app()
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_invalid_token(self):
        app, client = _make_app()
        resp = client.get("/api/v1/auth/me", headers={
            "Authorization": "Bearer invalid.token.here",
        })
        assert resp.status_code == 401
