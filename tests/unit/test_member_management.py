"""成员管理与邀请生命周期测试"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.auth import router as auth_router
from src.api.routers.orgs import router as orgs_router


class _FakePgStore:
    """模拟 PgStore 的用户/组织/成员/邀请方法"""

    def __init__(self):
        self._users = {}
        self._orgs = {}
        self._memberships = {}
        self._invitations = {}

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
            "org_id": org_id, "name": name, "description": description,
            "created_by": created_by, "created_at": None, "updated_at": None,
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
        return OrganizationRecord(**org) if org else None

    async def update_organization(self, org_id, name=None, description=None):
        from src.models.documents import OrganizationRecord

        org = self._orgs.get(org_id)
        if not org:
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
            "membership_id": membership_id, "org_id": org_id,
            "user_id": user_id, "role": role,
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
                    membership_id=m["membership_id"], org_id=m["org_id"],
                    user_id=m["user_id"], role=m["role"],
                    org_name=org.get("name", ""), joined_at=None,
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
                    membership_id=m["membership_id"], org_id=m["org_id"],
                    user_id=m["user_id"], role=m["role"],
                    username=user_data["username"] if user_data else "",
                    display_name=user_data.get("display_name") if user_data else None,
                    joined_at=None,
                ))
        return result

    async def update_membership_role(self, membership_id, role):
        if membership_id in self._memberships:
            self._memberships[membership_id]["role"] = role
            return True
        return False

    async def delete_membership(self, org_id, user_id):
        for key, m in list(self._memberships.items()):
            if m["org_id"] == org_id and m["user_id"] == user_id:
                del self._memberships[key]
                return True
        return False

    async def count_members_by_role(self, org_id, role):
        count = 0
        for m in self._memberships.values():
            if m["org_id"] == org_id and m["role"] == role:
                count += 1
        return count

    # ---- 邀请 ----
    async def create_invitation(self, invitation_id, org_id, inviter_user_id, invitee_user_id):
        from src.models.documents import InvitationRecord

        self._invitations[invitation_id] = {
            "invitation_id": invitation_id, "org_id": org_id,
            "inviter_user_id": inviter_user_id, "invitee_user_id": invitee_user_id,
            "status": "pending", "created_at": datetime.now(timezone.utc),
            "responded_at": None,
        }
        return InvitationRecord(**self._invitations[invitation_id])

    async def get_pending_invitation(self, org_id, invitee_user_id):
        from src.models.documents import InvitationRecord

        for inv in self._invitations.values():
            if inv["org_id"] == org_id and inv["invitee_user_id"] == invitee_user_id and inv["status"] == "pending":
                return InvitationRecord(**inv)
        return None

    async def get_invitation(self, invitation_id):
        from src.models.documents import InvitationRecord

        inv = self._invitations.get(invitation_id)
        return InvitationRecord(**inv) if inv else None

    async def list_invitations_by_user(self, user_id):
        from src.models.documents import InvitationRecord

        result = []
        for inv in self._invitations.values():
            if inv["invitee_user_id"] == user_id:
                org = self._orgs.get(inv["org_id"], {})
                inviter = None
                for u in self._users.values():
                    if u["user_id"] == inv["inviter_user_id"]:
                        inviter = u
                        break
                result.append(InvitationRecord(
                    invitation_id=inv["invitation_id"], org_id=inv["org_id"],
                    inviter_user_id=inv["inviter_user_id"], invitee_user_id=inv["invitee_user_id"],
                    status=inv["status"], org_name=org.get("name", ""),
                    inviter_username=inviter["username"] if inviter else "",
                    created_at=inv["created_at"], responded_at=inv["responded_at"],
                ))
        return result

    async def update_invitation_status(self, invitation_id, status, responded_at=None):
        if invitation_id in self._invitations:
            self._invitations[invitation_id]["status"] = status
            self._invitations[invitation_id]["responded_at"] = responded_at or datetime.now(timezone.utc)
            return True
        return False


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


def _create_org_and_get_id(client, token, name="team-a"):
    resp = client.post("/api/v1/orgs", json={"name": name}, headers=_auth_header(token))
    return resp.json()["org_id"]


class TestInviteMember:
    def test_admin_invites_registered_user(self):
        """Given 管理员邀请已注册用户名，Then 创建 pending 邀请返回 201"""
        app, client = _make_app()
        token_admin = _register_and_get_token(client, "admin")
        _register_and_get_token(client, "bob")
        org_id = _create_org_and_get_id(client, token_admin)

        resp = client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"username": "bob"},
            headers=_auth_header(token_admin),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["invitee_user_id"] != ""

    def test_invite_nonexistent_user_returns_404(self):
        """Given 管理员邀请不存在的用户名，Then 返回 404"""
        app, client = _make_app()
        token = _register_and_get_token(client)
        org_id = _create_org_and_get_id(client, token)

        resp = client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"username": "nosuchuser"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 404

    def test_duplicate_pending_invitation_returns_409(self):
        """Given 被邀请者已有 pending 邀请，When 管理员重复邀请，Then 返回 409"""
        app, client = _make_app()
        token_admin = _register_and_get_token(client, "admin")
        _register_and_get_token(client, "bob")
        org_id = _create_org_and_get_id(client, token_admin)

        client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"username": "bob"},
            headers=_auth_header(token_admin),
        )
        resp = client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"username": "bob"},
            headers=_auth_header(token_admin),
        )
        assert resp.status_code == 409

    def test_invite_existing_member_returns_409(self):
        """Given 用户已在组织中，When 管理员邀请该用户，Then 返回 409"""
        app, client = _make_app()
        token_admin = _register_and_get_token(client, "admin")
        token_bob = _register_and_get_token(client, "bob")
        org_id = _create_org_and_get_id(client, token_admin)

        # bob 加入组织（通过接受邀请）
        inv_resp = client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"username": "bob"},
            headers=_auth_header(token_admin),
        )
        inv_id = inv_resp.json()["invitation_id"]
        client.post(
            f"/api/v1/auth/invitations/{inv_id}/accept",
            headers=_auth_header(token_bob),
        )

        resp = client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"username": "bob"},
            headers=_auth_header(token_admin),
        )
        assert resp.status_code == 409

    def test_non_admin_cannot_invite(self):
        """Given 非管理员调用邀请端点，Then 返回 403"""
        app, client = _make_app()
        token_admin = _register_and_get_token(client, "admin")
        token_bob = _register_and_get_token(client, "bob")
        org_id = _create_org_and_get_id(client, token_admin)

        # bob 加入组织成为 member
        inv_resp = client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"username": "bob"},
            headers=_auth_header(token_admin),
        )
        inv_id = inv_resp.json()["invitation_id"]
        client.post(
            f"/api/v1/auth/invitations/{inv_id}/accept",
            headers=_auth_header(token_bob),
        )

        # bob 作为普通成员尝试邀请
        resp = client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"username": "charlie"},
            headers=_auth_header(token_bob),
        )
        assert resp.status_code == 403


class TestListInvitations:
    def test_invitee_sees_pending_invitation(self):
        """Given 被邀请者有 pending 邀请，When 调用 GET /auth/invitations，Then 列表中包含该邀请"""
        app, client = _make_app()
        token_admin = _register_and_get_token(client, "admin")
        token_bob = _register_and_get_token(client, "bob")
        org_id = _create_org_and_get_id(client, token_admin)

        client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"username": "bob"},
            headers=_auth_header(token_admin),
        )

        resp = client.get("/api/v1/auth/invitations", headers=_auth_header(token_bob))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "pending"
        assert data[0]["org_name"] == "team-a"


class TestAcceptInvitation:
    def test_accept_creates_membership(self):
        """Given 被邀请者接受邀请，Then 成员关系建立，角色为 member"""
        app, client = _make_app()
        token_admin = _register_and_get_token(client, "admin")
        token_bob = _register_and_get_token(client, "bob")
        org_id = _create_org_and_get_id(client, token_admin)

        inv_resp = client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"username": "bob"},
            headers=_auth_header(token_admin),
        )
        inv_id = inv_resp.json()["invitation_id"]

        resp = client.post(
            f"/api/v1/auth/invitations/{inv_id}/accept",
            headers=_auth_header(token_bob),
        )
        assert resp.status_code == 200

        # 验证成员列表
        members = client.get(
            f"/api/v1/orgs/{org_id}/members",
            headers=_auth_header(token_admin),
        )
        assert len(members.json()) == 2
        roles = {m["role"] for m in members.json()}
        assert roles == {"admin", "member"}


class TestRejectInvitation:
    def test_reject_changes_status(self):
        """Given 被邀请者拒绝邀请，Then 邀请状态变为 rejected"""
        app, client = _make_app()
        token_admin = _register_and_get_token(client, "admin")
        token_bob = _register_and_get_token(client, "bob")
        org_id = _create_org_and_get_id(client, token_admin)

        inv_resp = client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"username": "bob"},
            headers=_auth_header(token_admin),
        )
        inv_id = inv_resp.json()["invitation_id"]

        resp = client.post(
            f"/api/v1/auth/invitations/{inv_id}/reject",
            headers=_auth_header(token_bob),
        )
        assert resp.status_code == 200

        # 再次接受应返回 410
        resp2 = client.post(
            f"/api/v1/auth/invitations/{inv_id}/accept",
            headers=_auth_header(token_bob),
        )
        assert resp2.status_code == 410


class TestChangeRole:
    def test_admin_changes_member_role(self):
        """Given 管理员变更成员角色，Then 角色更新成功"""
        app, client = _make_app()
        token_admin = _register_and_get_token(client, "admin")
        token_bob = _register_and_get_token(client, "bob")
        org_id = _create_org_and_get_id(client, token_admin)

        # 先让 bob 加入组织
        inv_resp = client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"username": "bob"},
            headers=_auth_header(token_admin),
        )
        inv_id = inv_resp.json()["invitation_id"]
        client.post(
            f"/api/v1/auth/invitations/{inv_id}/accept",
            headers=_auth_header(token_bob),
        )

        # 获取 bob 的 membership/user_id
        bob_user_id = None
        members_resp = client.get(
            f"/api/v1/orgs/{org_id}/members",
            headers=_auth_header(token_admin),
        )
        for m in members_resp.json():
            if m["username"] == "bob":
                bob_user_id = m["user_id"]
                break

        resp = client.patch(
            f"/api/v1/orgs/{org_id}/members/{bob_user_id}",
            json={"role": "admin"},
            headers=_auth_header(token_admin),
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"


class TestRemoveMember:
    def test_admin_removes_member(self):
        """Given 管理员移除成员，Then 成员关系删除"""
        app, client = _make_app()
        token_admin = _register_and_get_token(client, "admin")
        token_bob = _register_and_get_token(client, "bob")
        org_id = _create_org_and_get_id(client, token_admin)

        inv_resp = client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"username": "bob"},
            headers=_auth_header(token_admin),
        )
        inv_id = inv_resp.json()["invitation_id"]
        client.post(
            f"/api/v1/auth/invitations/{inv_id}/accept",
            headers=_auth_header(token_bob),
        )

        bob_user_id = None
        members_resp = client.get(
            f"/api/v1/orgs/{org_id}/members",
            headers=_auth_header(token_admin),
        )
        for m in members_resp.json():
            if m["username"] == "bob":
                bob_user_id = m["user_id"]
                break

        resp = client.delete(
            f"/api/v1/orgs/{org_id}/members/{bob_user_id}",
            headers=_auth_header(token_admin),
        )
        assert resp.status_code == 200

        # 验证 bob 已不在成员列表中
        members = client.get(
            f"/api/v1/orgs/{org_id}/members",
            headers=_auth_header(token_admin),
        )
        assert len(members.json()) == 1


class TestLeaveOrg:
    def test_regular_member_can_leave(self):
        """Given 普通成员退出组织，Then 退出成功"""
        app, client = _make_app()
        token_admin = _register_and_get_token(client, "admin")
        token_bob = _register_and_get_token(client, "bob")
        org_id = _create_org_and_get_id(client, token_admin)

        inv_resp = client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"username": "bob"},
            headers=_auth_header(token_admin),
        )
        inv_id = inv_resp.json()["invitation_id"]
        client.post(
            f"/api/v1/auth/invitations/{inv_id}/accept",
            headers=_auth_header(token_bob),
        )

        resp = client.delete(
            f"/api/v1/orgs/{org_id}/members/me",
            headers=_auth_header(token_bob),
        )
        assert resp.status_code == 200

    def test_sole_admin_cannot_leave(self):
        """Given 唯一管理员退出组织，Then 返回 403"""
        app, client = _make_app()
        token_admin = _register_and_get_token(client, "admin")
        org_id = _create_org_and_get_id(client, token_admin)

        resp = client.delete(
            f"/api/v1/orgs/{org_id}/members/me",
            headers=_auth_header(token_admin),
        )
        assert resp.status_code == 403


class TestAdminCannotRemoveSelf:
    def test_admin_cannot_remove_self(self):
        """Given 管理员尝试移除自己，Then 返回 403"""
        app, client = _make_app()
        token_admin = _register_and_get_token(client, "admin")
        org_id = _create_org_and_get_id(client, token_admin)

        resp = client.delete(
            f"/api/v1/orgs/{org_id}/members/me",  # /me endpoint works for self-removal via leave
            headers=_auth_header(token_admin),
        )
        # Sole admin cannot leave
        assert resp.status_code == 403


class TestInvitationExpiry:
    def test_expired_invitation_accept_returns_410(self):
        """Given 邀请超过 7 天未响应，When 接受邀请，Then 返回 410"""
        app, client = _make_app()
        token_admin = _register_and_get_token(client, "admin")
        token_bob = _register_and_get_token(client, "bob")
        org_id = _create_org_and_get_id(client, token_admin)

        inv_resp = client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"username": "bob"},
            headers=_auth_header(token_admin),
        )
        inv_id = inv_resp.json()["invitation_id"]

        # Manually set the created_at to 8 days ago in the fake store
        pg_store_obj = client.app.state.pg_store
        pg_store_obj._invitations[inv_id]["created_at"] = datetime.now(timezone.utc) - timedelta(days=8)

        resp = client.post(
            f"/api/v1/auth/invitations/{inv_id}/accept",
            headers=_auth_header(token_bob),
        )
        assert resp.status_code == 410

    def test_expired_invitation_reject_returns_410(self):
        """Given 邀请超过 7 天未响应，When 拒绝邀请，Then 返回 410"""
        app, client = _make_app()
        token_admin = _register_and_get_token(client, "admin")
        token_bob = _register_and_get_token(client, "bob")
        org_id = _create_org_and_get_id(client, token_admin)

        inv_resp = client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"username": "bob"},
            headers=_auth_header(token_admin),
        )
        inv_id = inv_resp.json()["invitation_id"]

        pg_store_obj = client.app.state.pg_store
        pg_store_obj._invitations[inv_id]["created_at"] = datetime.now(timezone.utc) - timedelta(days=8)

        resp = client.post(
            f"/api/v1/auth/invitations/{inv_id}/reject",
            headers=_auth_header(token_bob),
        )
        assert resp.status_code == 410

    def test_expired_invitation_shows_expired_in_list(self):
        """Given 邀请超过 7 天，When 查询邀请列表，Then 标记为 expired"""
        app, client = _make_app()
        token_admin = _register_and_get_token(client, "admin")
        token_bob = _register_and_get_token(client, "bob")
        org_id = _create_org_and_get_id(client, token_admin)

        inv_resp = client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"username": "bob"},
            headers=_auth_header(token_admin),
        )
        inv_id = inv_resp.json()["invitation_id"]

        pg_store_obj = client.app.state.pg_store
        pg_store_obj._invitations[inv_id]["created_at"] = datetime.now(timezone.utc) - timedelta(days=8)

        resp = client.get("/api/v1/auth/invitations", headers=_auth_header(token_bob))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["expired"] is True
        assert data[0]["status"] == "expired"
