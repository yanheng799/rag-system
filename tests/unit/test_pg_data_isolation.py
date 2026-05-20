"""PG 数据隔离测试 — org_id 字段与权限控制"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers import documents, datasets

# 强制开启鉴权以测试隔离逻辑
from src.config.settings import settings
settings.auth_enabled = True


class _FakePgStore:
    """模拟 PgStore — 支持 org_id 和权限"""

    def __init__(self):
        self._users = {}
        self._orgs = {}
        self._memberships = {}
        self._datasets = {}
        self._documents = {}
        self._chunks = {}

    # ---- 用户/组织/成员 ----
    async def create_user(self, user_id, username, password_hash, display_name=None):
        from src.models.documents import UserRecord
        self._users[username] = {"user_id": user_id, "username": username, "password_hash": password_hash, "display_name": display_name}
        return UserRecord(user_id=user_id, username=username, display_name=display_name, created_at=None)

    async def get_user_by_username(self, username):
        from src.models.documents import UserRecord
        d = self._users.get(username)
        if not d: return None
        r = UserRecord(user_id=d["user_id"], username=d["username"], display_name=d["display_name"], created_at=None)
        r._password_hash = d["password_hash"]
        return r

    async def get_user_by_id(self, user_id):
        from src.models.documents import UserRecord
        for d in self._users.values():
            if d["user_id"] == user_id:
                r = UserRecord(user_id=d["user_id"], username=d["username"], display_name=d["display_name"], created_at=None)
                r._password_hash = d["password_hash"]
                return r
        return None

    async def get_user_memberships(self, user_id):
        from src.models.documents import MembershipRecord
        return [MembershipRecord(membership_id=m["membership_id"], org_id=m["org_id"], user_id=m["user_id"], role=m["role"], org_name=self._orgs.get(m["org_id"], {}).get("name", ""), joined_at=None) for m in self._memberships.values() if m["user_id"] == user_id]

    async def create_organization(self, org_id, name, created_by, description=None):
        from src.models.documents import OrganizationRecord
        self._orgs[org_id] = {"org_id": org_id, "name": name, "description": description, "created_by": created_by}
        return OrganizationRecord(**self._orgs[org_id])

    async def get_organization(self, org_id):
        from src.models.documents import OrganizationRecord
        o = self._orgs.get(org_id); return OrganizationRecord(**o) if o else None

    async def create_membership(self, membership_id, org_id, user_id, role="member"):
        from src.models.documents import MembershipRecord
        self._memberships[membership_id] = {"membership_id": membership_id, "org_id": org_id, "user_id": user_id, "role": role}
        return MembershipRecord(**self._memberships[membership_id], org_name="", joined_at=None)

    async def get_membership(self, org_id, user_id):
        from src.models.documents import MembershipRecord
        for m in self._memberships.values():
            if m["org_id"] == org_id and m["user_id"] == user_id:
                return MembershipRecord(membership_id=m["membership_id"], org_id=m["org_id"], user_id=m["user_id"], role=m["role"], joined_at=None)
        return None

    async def get_organization_by_name(self, name):
        from src.models.documents import OrganizationRecord
        for o in self._orgs.values():
            if o["name"] == name:
                return OrganizationRecord(**o)
        return None

    async def list_memberships_by_user(self, user_id):
        from src.models.documents import MembershipRecord
        return [MembershipRecord(membership_id=m["membership_id"], org_id=m["org_id"], user_id=m["user_id"], role=m["role"], org_name=self._orgs.get(m["org_id"], {}).get("name", ""), joined_at=None) for m in self._memberships.values() if m["user_id"] == user_id]

    async def list_members_by_org(self, org_id):
        from src.models.documents import MembershipRecord
        result = []
        for m in self._memberships.values():
            if m["org_id"] == org_id:
                u = next((v for v in self._users.values() if v["user_id"] == m["user_id"]), None)
                result.append(MembershipRecord(membership_id=m["membership_id"], org_id=m["org_id"], user_id=m["user_id"], role=m["role"], username=u["username"] if u else "", display_name=u.get("display_name") if u else None, joined_at=None))
        return result

    async def get_pending_invitation(self, org_id, invitee_user_id):
        from src.models.documents import InvitationRecord
        self._invitations = getattr(self, '_invitations', {})
        for inv in self._invitations.values():
            if inv["org_id"] == org_id and inv["invitee_user_id"] == invitee_user_id and inv["status"] == "pending":
                return InvitationRecord(**inv)
        return None

    async def create_invitation(self, invitation_id, org_id, inviter_user_id, invitee_user_id):
        from src.models.documents import InvitationRecord
        import datetime
        self._invitations = getattr(self, '_invitations', {})
        self._invitations[invitation_id] = {"invitation_id": invitation_id, "org_id": org_id, "inviter_user_id": inviter_user_id, "invitee_user_id": invitee_user_id, "status": "pending", "created_at": datetime.datetime.now(datetime.timezone.utc), "responded_at": None}
        return InvitationRecord(**self._invitations[invitation_id])

    async def get_invitation(self, invitation_id):
        from src.models.documents import InvitationRecord
        self._invitations = getattr(self, '_invitations', {})
        inv = self._invitations.get(invitation_id)
        return InvitationRecord(**inv) if inv else None

    async def list_invitations_by_user(self, user_id):
        return []

    async def update_invitation_status(self, invitation_id, status, responded_at=None):
        self._invitations = getattr(self, '_invitations', {})
        if invitation_id in self._invitations:
            self._invitations[invitation_id]["status"] = status
        return True

    async def update_organization(self, org_id, name=None, description=None):
        return await self.get_organization(org_id)

    # ---- 数据集 ----
    async def create_dataset(self, dataset_id, name, description=None, org_id=None, created_by=None):
        from src.models.documents import DatasetRecord
        self._datasets[dataset_id] = {"dataset_id": dataset_id, "name": name, "description": description, "org_id": org_id, "created_by": created_by, "created_at": None, "updated_at": None}
        return DatasetRecord(**self._datasets[dataset_id])

    async def get_dataset(self, dataset_id):
        from src.models.documents import DatasetRecord
        d = self._datasets.get(dataset_id); return DatasetRecord(**d) if d else None

    async def list_datasets(self, page=1, size=20, org_id=None):
        from src.models.documents import DatasetRecord
        items = [DatasetRecord(**d) for d in self._datasets.values() if org_id is None or d.get("org_id") == org_id]
        return items, len(items)

    async def count_docs_by_dataset(self, dataset_id, org_id=None):
        return len([d for d in self._documents.values() if d["dataset_id"] == dataset_id and (org_id is None or d.get("org_id") == org_id)])

    async def get_doc_ids_by_dataset_ids(self, dataset_ids, org_id=None):
        return [d["doc_id"] for d in self._documents.values() if d.get("dataset_id") in dataset_ids and (org_id is None or d.get("org_id") == org_id)]

    async def get_doc_ids_by_filenames(self, filenames, org_id=None):
        return [d["doc_id"] for d in self._documents.values() if any(f in d["filename"] for f in filenames) and (org_id is None or d.get("org_id") == org_id)]

    async def update_dataset(self, dataset_id, name=None, description=None):
        from src.models.documents import DatasetRecord
        d = self._datasets.get(dataset_id)
        if d:
            if name is not None: d["name"] = name
            if description is not None: d["description"] = description
        return DatasetRecord(**d) if d else None

    async def delete_dataset(self, dataset_id):
        return self._datasets.pop(dataset_id, None) is not None

    # ---- 文档 ----
    async def save_document(self, doc):
        self._documents[doc.doc_id] = {
            "doc_id": doc.doc_id, "dataset_id": doc.dataset_id, "org_id": doc.org_id,
            "content_hash": doc.content_hash, "filename": doc.filename,
            "raw_file_url": doc.raw_file_url, "file_size": doc.file_size,
            "file_type": doc.file_type, "status": doc.status, "error_msg": None,
            "retry_count": 0, "created_by": doc.created_by, "chunk_count": 0,
            "chunk_options": None, "uploaded_at": None, "updated_at": None,
        }

    async def get_document(self, doc_id):
        from src.models.documents import DocumentRecord
        d = self._documents.get(doc_id)
        return DocumentRecord(**d) if d else None

    async def get_document_by_hash(self, content_hash):
        from src.models.documents import DocumentRecord
        for d in self._documents.values():
            if d["content_hash"] == content_hash:
                return DocumentRecord(**d)
        return None

    async def list_documents(self, page=1, size=20, dataset_id=None, org_id=None):
        from src.models.documents import DocumentRecord
        items = [d for d in self._documents.values() if (dataset_id is None or d.get("dataset_id") == dataset_id) and (org_id is None or d.get("org_id") == org_id)]
        return [DocumentRecord(**d) for d in items], len(items)

    async def update_status(self, doc_id, status, error_msg=None, chunk_options=None):
        if doc_id in self._documents:
            self._documents[doc_id]["status"] = status

    async def delete_document(self, doc_id):
        return self._documents.pop(doc_id, None) is not None

    async def delete_chunks_by_doc(self, doc_id):
        self._chunks = {k: v for k, v in self._chunks.items() if v["doc_id"] != doc_id}
        return 0

    async def get_chunk(self, chunk_id):
        return None


def _make_app(*, with_documents=True, with_datasets=True):
    app = FastAPI()
    app.state.pg_store = _FakePgStore()
    app.state.oss_store = type("FakeOSS", (), {"upload_raw_doc": lambda *a, **kw: None, "download": lambda s, p: b"fake"})()
    app.state.milvus_store = type("FakeMV", (), {"delete_by_doc_id": lambda *a: None, "delete_by_chunk_ids": lambda *a: None})()
    app.state.embedder = type("FakeEmb", (), {})()
    if with_documents:
        app.include_router(documents.router)
    if with_datasets:
        app.include_router(datasets.router)
    return app, TestClient(app)


class TestDocumentOrgIsolation:
    """文档 org_id 隔离测试"""

    def _setup_org(self, client, admin="admin", member="member", org_name="team-a"):
        """设置组织：注册用户 → 创建组织 → 成员加入，返回 token"""
        from src.api.routers.auth import router as auth_router
        from src.api.routers.orgs import router as orgs_router
        client.app.include_router(auth_router)
        client.app.include_router(orgs_router)

        client.post("/api/v1/auth/register", json={"username": admin, "password": "secret123"})
        resp = client.post("/api/v1/auth/login", json={"username": admin, "password": "secret123"})
        token_admin = resp.json()["access_token"]

        client.post("/api/v1/auth/register", json={"username": member, "password": "secret123"})
        resp = client.post("/api/v1/auth/login", json={"username": member, "password": "secret123"})
        token_member = resp.json()["access_token"]

        org_resp = client.post("/api/v1/orgs", json={"name": org_name}, headers={"Authorization": f"Bearer {token_admin}"})
        org_id = org_resp.json()["org_id"]

        # admin switch-org
        resp = client.post("/api/v1/auth/switch-org", json={"org_id": org_id}, headers={"Authorization": f"Bearer {token_admin}"})
        token_admin = resp.json()["access_token"]

        # invite member
        inv_resp = client.post(f"/api/v1/orgs/{org_id}/invitations", json={"username": member}, headers={"Authorization": f"Bearer {token_admin}"})
        inv_id = inv_resp.json()["invitation_id"]
        client.post(f"/api/v1/auth/invitations/{inv_id}/accept", headers={"Authorization": f"Bearer {token_member}"})
        resp = client.post("/api/v1/auth/switch-org", json={"org_id": org_id}, headers={"Authorization": f"Bearer {token_member}"})
        token_member = resp.json()["access_token"]

        return org_id, token_admin, token_member

    def test_upload_doc_has_org_id(self):
        """Given 用户属于组织 Alpha，When 上传文档，Then 文档 org_id 为 Alpha 的 org_id"""
        app, client = _make_app()
        org_id, token_admin, _ = self._setup_org(client)

        with __import__("io").BytesIO(b"test content") as f:
            resp = client.post("/api/v1/documents", files=[("files", ("test.txt", f, "text/plain"))], data={"dataset_id": ""}, headers={"Authorization": f"Bearer {token_admin}"})

        assert resp.status_code == 200
        doc_id = resp.json()[0]["doc_id"]
        doc = client.app.state.pg_store._documents[doc_id]
        assert doc["org_id"] == org_id

    def test_list_documents_filtered_by_org(self):
        """Given 组织 Alpha 有文档 D1，组织 Beta 有文档 D2，When Alpha 用户查询，Then 只看到 D1"""
        app, client = _make_app()
        org_alpha, token_alpha, _ = self._setup_org(client, admin="admin_a", member="mem_a", org_name="team-a")

        # 创建组织 Beta
        client.post("/api/v1/auth/register", json={"username": "admin_b", "password": "secret123"})
        resp = client.post("/api/v1/auth/login", json={"username": "admin_b", "password": "secret123"})
        token_b = resp.json()["access_token"]
        org_resp = client.post("/api/v1/orgs", json={"name": "team-b"}, headers={"Authorization": f"Bearer {token_b}"})
        org_beta = org_resp.json()["org_id"]
        resp = client.post("/api/v1/auth/switch-org", json={"org_id": org_beta}, headers={"Authorization": f"Bearer {token_b}"})
        token_b = resp.json()["access_token"]

        # Alpha 上传 doc1
        with __import__("io").BytesIO(b"content 1") as f:
            client.post("/api/v1/documents", files=[("files", ("doc1.txt", f, "text/plain"))], data={"dataset_id": ""}, headers={"Authorization": f"Bearer {token_alpha}"})

        # Beta 上传 doc2
        with __import__("io").BytesIO(b"content 2") as f:
            client.post("/api/v1/documents", files=[("files", ("doc2.txt", f, "text/plain"))], data={"dataset_id": ""}, headers={"Authorization": f"Bearer {token_b}"})

        # Alpha 用户查询
        resp = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token_alpha}"})
        assert resp.status_code == 200
        items = resp.json()["items"]
        filenames = {i["filename"] for i in items}
        assert "doc1.txt" in filenames
        assert "doc2.txt" not in filenames

    def test_member_cannot_delete_other_doc(self):
        """Given 普通成员尝试删除他人上传的文档，Then 返回 403"""
        app, client = _make_app()
        org_id, token_admin, token_member = self._setup_org(client)

        # Admin 上传文档
        with __import__("io").BytesIO(b"admin doc") as f:
            resp = client.post("/api/v1/documents", files=[("files", ("admin.txt", f, "text/plain"))], data={"dataset_id": ""}, headers={"Authorization": f"Bearer {token_admin}"})
        doc_id = resp.json()[0]["doc_id"]

        # Member 尝试删除
        resp = client.delete(f"/api/v1/documents/{doc_id}", headers={"Authorization": f"Bearer {token_member}"})
        assert resp.status_code == 403

    def test_admin_can_delete_any_doc(self):
        """Given 管理员删除本组织任意文档，When 调用 DELETE，Then 返回 200"""
        app, client = _make_app()
        org_id, token_admin, token_member = self._setup_org(client)

        # Member 上传文档
        with __import__("io").BytesIO(b"member doc") as f:
            resp = client.post("/api/v1/documents", files=[("files", ("member.txt", f, "text/plain"))], data={"dataset_id": ""}, headers={"Authorization": f"Bearer {token_member}"})
        doc_id = resp.json()[0]["doc_id"]

        # Admin 删除
        resp = client.delete(f"/api/v1/documents/{doc_id}", headers={"Authorization": f"Bearer {token_admin}"})
        assert resp.status_code == 200

    def test_members_see_all_org_docs_in_list(self):
        """Given 普通成员上传了文档 D1，其他成员上传了 D2，When 查询文档列表，Then 能看到 D1 和 D2"""
        app, client = _make_app()
        org_id, token_admin, token_member = self._setup_org(client, admin="admin", member="member")

        # 第二个成员
        client.post("/api/v1/auth/register", json={"username": "member2", "password": "secret123"})
        resp = client.post("/api/v1/auth/login", json={"username": "member2", "password": "secret123"})
        token_member2_raw = resp.json()["access_token"]
        inv_resp = client.post(f"/api/v1/orgs/{org_id}/invitations", json={"username": "member2"}, headers={"Authorization": f"Bearer {token_admin}"})
        client.post(f"/api/v1/auth/invitations/{inv_resp.json()['invitation_id']}/accept", headers={"Authorization": f"Bearer {token_member2_raw}"})
        resp = client.post("/api/v1/auth/switch-org", json={"org_id": org_id}, headers={"Authorization": f"Bearer {token_member2_raw}"})
        token_member2 = resp.json()["access_token"]

        # member 上传 D1
        with __import__("io").BytesIO(b"d1") as f:
            client.post("/api/v1/documents", files=[("files", ("d1.txt", f, "text/plain"))], data={"dataset_id": ""}, headers={"Authorization": f"Bearer {token_member}"})
        # member2 上传 D2
        with __import__("io").BytesIO(b"d2") as f:
            client.post("/api/v1/documents", files=[("files", ("d2.txt", f, "text/plain"))], data={"dataset_id": ""}, headers={"Authorization": f"Bearer {token_member2}"})

        # member 查询列表 → 看到 D1 和 D2
        resp = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token_member}"})
        assert resp.status_code == 200
        filenames = {i["filename"] for i in resp.json()["items"]}
        assert filenames == {"d1.txt", "d2.txt"}

    def test_document_status_restricted_by_org(self):
        """Given 文档属于组织 Alpha，When 组织 Beta 用户查询其状态，Then 返回 404"""
        app, client = _make_app()
        org_alpha, token_alpha, _ = self._setup_org(client, admin="admin_a", member="mem_a", org_name="team-a")

        # 创建组织 Beta
        client.post("/api/v1/auth/register", json={"username": "admin_b", "password": "secret123"})
        resp = client.post("/api/v1/auth/login", json={"username": "admin_b", "password": "secret123"})
        token_b = resp.json()["access_token"]
        resp = client.post("/api/v1/orgs", json={"name": "team-b"}, headers={"Authorization": f"Bearer {token_b}"})
        org_beta = resp.json()["org_id"]
        resp = client.post("/api/v1/auth/switch-org", json={"org_id": org_beta}, headers={"Authorization": f"Bearer {token_b}"})
        token_b = resp.json()["access_token"]

        # Alpha 上传 doc
        with __import__("io").BytesIO(b"content") as f:
            resp = client.post("/api/v1/documents", files=[("files", ("doc.txt", f, "text/plain"))], data={"dataset_id": ""}, headers={"Authorization": f"Bearer {token_alpha}"})
        doc_id = resp.json()[0]["doc_id"]

        # Beta 用户查询 → 404
        resp = client.get(f"/api/v1/documents/{doc_id}/status", headers={"Authorization": f"Bearer {token_b}"})
        assert resp.status_code == 404


class TestDatasetOrgIsolation:
    """数据集 org_id 隔离测试"""

    def _setup_org(self, client, admin="admin", org_name="team-a"):
        from src.api.routers.auth import router as auth_router
        from src.api.routers.orgs import router as orgs_router
        client.app.include_router(auth_router)
        client.app.include_router(orgs_router)

        client.post("/api/v1/auth/register", json={"username": admin, "password": "secret123"})
        resp = client.post("/api/v1/auth/login", json={"username": admin, "password": "secret123"})
        token = resp.json()["access_token"]
        org_resp = client.post("/api/v1/orgs", json={"name": org_name}, headers={"Authorization": f"Bearer {token}"})
        org_id = org_resp.json()["org_id"]
        resp = client.post("/api/v1/auth/switch-org", json={"org_id": org_id}, headers={"Authorization": f"Bearer {token}"})
        return org_id, resp.json()["access_token"]

    def test_create_dataset_has_org_id(self):
        """Given 用户属于组织 Alpha，When 创建数据集，Then 数据集 org_id 为 Alpha 的 org_id"""
        app, client = _make_app()
        org_id, token = self._setup_org(client)

        resp = client.post("/api/v1/datasets", json={"name": "my-ds"}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201
        ds = client.app.state.pg_store._datasets[resp.json()["dataset_id"]]
        assert ds["org_id"] == org_id

    def test_list_datasets_filtered_by_org(self):
        """Given 组织 Alpha 有数据集 DS1，When 组织 Beta 的用户查询，Then 不包含 DS1"""
        app, client = _make_app()
        org_alpha, token_alpha = self._setup_org(client, admin="admin_a", org_name="team-a")

        # 创建组织 Beta
        client.post("/api/v1/auth/register", json={"username": "admin_b", "password": "secret123"})
        resp = client.post("/api/v1/auth/login", json={"username": "admin_b", "password": "secret123"})
        token_b = resp.json()["access_token"]
        org_resp = client.post("/api/v1/orgs", json={"name": "team-b"}, headers={"Authorization": f"Bearer {token_b}"})
        org_beta = org_resp.json()["org_id"]
        resp = client.post("/api/v1/auth/switch-org", json={"org_id": org_beta}, headers={"Authorization": f"Bearer {token_b}"})
        token_b = resp.json()["access_token"]

        # Alpha 创建 DS1
        client.post("/api/v1/datasets", json={"name": "ds-alpha"}, headers={"Authorization": f"Bearer {token_alpha}"})
        # Beta 创建 DS2
        client.post("/api/v1/datasets", json={"name": "ds-beta"}, headers={"Authorization": f"Bearer {token_b}"})

        # Alpha 查询
        resp = client.get("/api/v1/datasets", headers={"Authorization": f"Bearer {token_alpha}"})
        names = {i["name"] for i in resp.json()["items"]}
        assert "ds-alpha" in names
        assert "ds-beta" not in names

    def test_get_dataset_restricted_by_org(self):
        """Given 数据集属于 Alpha，When Beta 用户获取详情，Then 返回 404"""
        app, client = _make_app()
        org_alpha, token_alpha = self._setup_org(client, admin="admin_a", org_name="team-a")
        org_beta, token_b = self._setup_org(client, admin="admin_b", org_name="team-b")

        ds_resp = client.post("/api/v1/datasets", json={"name": "secret-ds"}, headers={"Authorization": f"Bearer {token_alpha}"})
        ds_id = ds_resp.json()["dataset_id"]

        resp = client.get(f"/api/v1/datasets/{ds_id}", headers={"Authorization": f"Bearer {token_b}"})
        assert resp.status_code == 404
