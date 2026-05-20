"""组织管理与成员关系测试"""

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth_utils import create_access_token, hash_password
from src.api.routers.auth import router as auth_router
from src.api.routers.orgs import router as orgs_router


class _FakePgStore:
    """模拟 PgStore 的用户/组织/成员方法"""

    def __init__(self):
        self._users = {}
        self._orgs = {}  # org_id -> dict
        self._memberships = {}  # membership_id -> dict

    # ---- 用户 ----
    async def create_user(self, user_id, username, password_hash, display_name=None):
        from src.models.documents import UserRecord

        self._users[username] = {
            "user_id": user_id,
            "username": username,
            "password_hash": password_hash,
            "display_name": display_name,
        }
        return UserRecord(user_id=user_id, username=username, display_name=display_name, created_at=None)

    async def get_user_by_username(self, username):
        from src.models.documents import UserRecord

        data = self._users.get(username)
        if not data:
            return None
        rec = UserRecord(user_id=data["user_id"], username=data["username"], display_name=data["display_name"], created_at=None)
        rec._password_hash = data["password_hash"]
        return rec

    async def get_user_by_id(self, user_id):
        from src.models.documents import UserRecord

        for data in self._users.values():
            if data["user_id"] == user_id:
                rec = UserRecord(user_id=data["user_id"], username=data["username"], display_name=data["display_name"], created_at=None)
                rec._password_hash = data["password_hash"]
                return rec
        return None

    async def get_user_memberships(self, user_id):
        from src.models.documents import MembershipRecord

        result = []
        for m in self._memberships.values():
            if m["user_id"] == user_id:
                org = self._orgs.get(m["org_id"], {})
                result.append(MembershipRecord(
                    membership_id=m["membership_id"],
                    org_id=m["org_id"],
                    user_id=m["user_id"],
                    role=m["role"],
                    org_name=org.get("name", ""),
                    joined_at=None,
                ))
        return result

    # ---- 组织 ----
    async def create_organization(self, org_id, name, created_by, description=None):
        from src.models.documents import OrganizationRecord

        self._orgs[org_id] = {
            "org_id": org_id,
            "name": name,
            "description": description,
            "created_by": created_by,
            "created_at": None,
            "updated_at": None,
        }
        return OrganizationRecord(**self._orgs[org_id])

    async def get_organization_by_name(self, name):
        from src.models.documents import OrganizationRecord

        for org in self._orgs.values():
            if org["name"] == name:
                return OrganizationRecord(**org)
        return None

    async def get_organization(self, org_id):
        from src.models.documents import OrganizationRecord

        org = self._orgs.get(org_id)
        if org is None:
            return None
        return OrganizationRecord(**org)

    async def update_organization(self, org_id, name=None, description=None):
        from src.models.documents import OrganizationRecord

        org = self._orgs.get(org_id)
        if org is None:
            return None
        if name is not None:
            org["name"] = name
        if description is not None:
            org["description"] = description
        return OrganizationRecord(**org)

    # ---- 成员 ----
    async def create_membership(self, membership_id, org_id, user_id, role="member"):
        from src.models.documents import MembershipRecord

        self._memberships[membership_id] = {
            "membership_id": membership_id,
            "org_id": org_id,
            "user_id": user_id,
            "role": role,
        }
        return MembershipRecord(**self._memberships[membership_id], org_name="", joined_at=None)

    async def get_membership(self, org_id, user_id):
        from src.models.documents import MembershipRecord

        for m in self._memberships.values():
            if m["org_id"] == org_id and m["user_id"] == user_id:
                return MembershipRecord(membership_id=m["membership_id"], org_id=m["org_id"], user_id=m["user_id"], role=m["role"], joined_at=None)
        return None

    async def list_memberships_by_user(self, user_id):
        from src.models.documents import MembershipRecord

        result = []
        for m in self._memberships.values():
            if m["user_id"] == user_id:
                org = self._orgs.get(m["org_id"], {})
                result.append(MembershipRecord(
                    membership_id=m["membership_id"],
                    org_id=m["org_id"],
                    user_id=m["user_id"],
                    role=m["role"],
                    org_name=org.get("name", ""),
                    joined_at=None,
                ))
        return result

    async def list_members_by_org(self, org_id):
        from src.models.documents import MembershipRecord

        result = []
        for m in self._memberships.values():
            if m["org_id"] == org_id:
                user_data = None
                for u in self._users.values():
                    if u["user_id"] == m["user_id"]:
                        user_data = u
                        break
                result.append(MembershipRecord(
                    membership_id=m["membership_id"],
                    org_id=m["org_id"],
                    user_id=m["user_id"],
                    role=m["role"],
                    username=user_data["username"] if user_data else "",
                    display_name=user_data.get("display_name") if user_data else None,
                    joined_at=None,
                ))
        return result


def _make_app():
    app = FastAPI()
    app.state.pg_store = _FakePgStore()
    app.include_router(auth_router)
    app.include_router(orgs_router)
    return app, TestClient(app)


def _register_and_get_token(client, username="alice", password="secret123"):
    client.post("/api/v1/auth/register", json={"username": username, "password": password})
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return resp.json()["access_token"]


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


class TestCreateOrg:
    def test_create_org_success_creator_is_admin(self):
        """Given 已登录用户，When 创建组织，Then 返回 201，创建者自动成为管理员"""
        app, client = _make_app()
        token = _register_and_get_token(client)

        resp = client.post("/api/v1/orgs", json={"name": "team-a", "description": "测试团队"}, headers=_auth_header(token))
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "team-a"
        assert data["role"] == "admin"
        assert data["org_id"].startswith("org_")

    def test_create_org_duplicate_name_returns_409(self):
        """Given 组织名已存在，When 创建同名组织，Then 返回 409"""
        app, client = _make_app()
        token = _register_and_get_token(client)

        client.post("/api/v1/orgs", json={"name": "team-a"}, headers=_auth_header(token))
        resp = client.post("/api/v1/orgs", json={"name": "team-a"}, headers=_auth_header(token))
        assert resp.status_code == 409

    def test_create_org_without_token_returns_401(self):
        """Given 未认证，When 创建组织，Then 返回 401"""
        app, client = _make_app()
        resp = client.post("/api/v1/orgs", json={"name": "team-a"})
        assert resp.status_code == 401


class TestListOrgs:
    def test_list_my_orgs(self):
        """Given 已登录用户属于 2 个组织，When 调用 GET /orgs，Then 返回 2 个组织"""
        app, client = _make_app()
        token = _register_and_get_token(client)

        client.post("/api/v1/orgs", json={"name": "team-a"}, headers=_auth_header(token))
        client.post("/api/v1/orgs", json={"name": "team-b"}, headers=_auth_header(token))

        resp = client.get("/api/v1/orgs", headers=_auth_header(token))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {org["name"] for org in data}
        assert names == {"team-a", "team-b"}


class TestGetOrg:
    def test_get_org_as_member_returns_detail(self):
        """Given 是组织成员，When 获取组织详情，Then 返回 200"""
        app, client = _make_app()
        token = _register_and_get_token(client)

        create_resp = client.post("/api/v1/orgs", json={"name": "team-a"}, headers=_auth_header(token))
        org_id = create_resp.json()["org_id"]

        resp = client.get(f"/api/v1/orgs/{org_id}", headers=_auth_header(token))
        assert resp.status_code == 200
        assert resp.json()["name"] == "team-a"

    def test_get_org_as_non_member_returns_403(self):
        """Given 不是组织成员，When 获取组织详情，Then 返回 403"""
        app, client = _make_app()
        token_alice = _register_and_get_token(client, "alice")

        create_resp = client.post("/api/v1/orgs", json={"name": "team-a"}, headers=_auth_header(token_alice))
        org_id = create_resp.json()["org_id"]

        token_bob = _register_and_get_token(client, "bob", "secret456")
        resp = client.get(f"/api/v1/orgs/{org_id}", headers=_auth_header(token_bob))
        assert resp.status_code == 403


class TestUpdateOrg:
    def test_update_org_as_admin(self):
        """Given 是管理员，When PATCH 更新描述，Then 返回 200"""
        app, client = _make_app()
        token = _register_and_get_token(client)

        create_resp = client.post("/api/v1/orgs", json={"name": "team-a"}, headers=_auth_header(token))
        org_id = create_resp.json()["org_id"]

        resp = client.patch(f"/api/v1/orgs/{org_id}", json={"description": "新的描述"}, headers=_auth_header(token))
        assert resp.status_code == 200
        assert resp.json()["description"] == "新的描述"


class TestSwitchOrg:
    def test_switch_org_as_member_returns_new_token(self):
        """Given 是组织成员，When switch-org，Then 返回绑定 org_id 的新 token"""
        app, client = _make_app()
        token = _register_and_get_token(client)

        create_resp = client.post("/api/v1/orgs", json={"name": "team-a"}, headers=_auth_header(token))
        org_id = create_resp.json()["org_id"]

        resp = client.post("/api/v1/auth/switch-org", json={"org_id": org_id}, headers=_auth_header(token))
        assert resp.status_code == 200
        new_token = resp.json()["access_token"]
        assert new_token != token

        from src.api.auth_utils import decode_access_token
        payload = decode_access_token(new_token)
        assert payload["org_id"] == org_id

    def test_switch_org_as_non_member_returns_403(self):
        """Given 不是组织成员，When switch-org，Then 返回 403"""
        app, client = _make_app()
        token_alice = _register_and_get_token(client, "alice")

        create_resp = client.post("/api/v1/orgs", json={"name": "team-a"}, headers=_auth_header(token_alice))
        org_id = create_resp.json()["org_id"]

        token_bob = _register_and_get_token(client, "bob", "secret456")
        resp = client.post("/api/v1/auth/switch-org", json={"org_id": org_id}, headers=_auth_header(token_bob))
        assert resp.status_code == 403


class TestListMembers:
    def test_list_members(self):
        """Given 是组织成员，When 获取成员列表，Then 返回含角色的列表"""
        app, client = _make_app()
        token = _register_and_get_token(client)

        create_resp = client.post("/api/v1/orgs", json={"name": "team-a"}, headers=_auth_header(token))
        org_id = create_resp.json()["org_id"]

        resp = client.get(f"/api/v1/orgs/{org_id}/members", headers=_auth_header(token))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["role"] == "admin"
        assert data[0]["username"] == "alice"

    def test_list_members_as_non_member_returns_403(self):
        """Given 不是组织成员，When 获取成员列表，Then 返回 403"""
        app, client = _make_app()
        token_alice = _register_and_get_token(client, "alice")

        create_resp = client.post("/api/v1/orgs", json={"name": "team-a"}, headers=_auth_header(token_alice))
        org_id = create_resp.json()["org_id"]

        token_bob = _register_and_get_token(client, "bob", "secret456")
        resp = client.get(f"/api/v1/orgs/{org_id}/members", headers=_auth_header(token_bob))
        assert resp.status_code == 403
