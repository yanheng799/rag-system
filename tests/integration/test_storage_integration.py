"""集成测试：PostgreSQL 存储 + Milvus + MinIO + Embedder"""

import uuid

import pytest

# ---- PostgreSQL 集成测试 ----


class TestPgStoreIntegration:
    """PostgreSQL 存储集成测试"""

    @pytest.fixture
    def pg_store(self):
        from src.storage.pg_store import PgStore

        return PgStore()

    def test_pg_store_init(self, pg_store):
        assert pg_store is not None

    @pytest.mark.asyncio
    async def test_save_and_get_document(self, pg_store):
        from src.models.documents import DocumentRecord

        doc_id = f"test_{uuid.uuid4().hex[:8]}"
        doc = DocumentRecord(
            doc_id=doc_id,
            filename="test.pdf",
            raw_file_url=f"raw-docs/{doc_id}/test.pdf",
            file_size=1024,
            file_type="pdf",
        )
        await pg_store.save_document(doc)

        result = await pg_store.get_document(doc_id)
        assert result is not None
        assert result.doc_id == doc_id
        assert result.filename == "test.pdf"
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_update_status(self, pg_store):
        from src.models.documents import DocumentRecord

        doc_id = f"test_{uuid.uuid4().hex[:8]}"
        doc = DocumentRecord(
            doc_id=doc_id,
            filename="test.pdf",
            raw_file_url=f"raw-docs/{doc_id}/test.pdf",
        )
        await pg_store.save_document(doc)
        await pg_store.update_status(doc_id, "done")

        result = await pg_store.get_document(doc_id)
        assert result.status == "done"

    @pytest.mark.asyncio
    async def test_update_status_with_chunk_options(self, pg_store):
        from src.models.documents import DocumentRecord

        doc_id = f"test_{uuid.uuid4().hex[:8]}"
        doc = DocumentRecord(
            doc_id=doc_id,
            filename="test.pdf",
            raw_file_url=f"raw-docs/{doc_id}/test.pdf",
        )
        await pg_store.save_document(doc)

        opts = {"strategy": "heading", "max_size": 2048}
        await pg_store.update_status(doc_id, "processing", chunk_options=opts)

        result = await pg_store.get_document(doc_id)
        assert result.status == "processing"
        assert result.chunk_options == {"strategy": "heading", "max_size": 2048}

    @pytest.mark.asyncio
    async def test_list_documents_returns_chunk_options(self, pg_store):
        from src.models.documents import DocumentRecord

        doc_id = f"test_{uuid.uuid4().hex[:8]}"
        await pg_store.save_document(
            DocumentRecord(
                doc_id=doc_id,
                filename="test.pdf",
                raw_file_url=f"raw-docs/{doc_id}/test.pdf",
            )
        )
        opts = {"strategy": "paragraph", "max_size": 1024, "vertical_gap": 20}
        await pg_store.update_status(doc_id, "processing", chunk_options=opts)

        records, _ = await pg_store.list_documents(size=100)
        found = next((r for r in records if r.doc_id == doc_id), None)
        assert found is not None
        assert found.chunk_options == {"strategy": "paragraph", "max_size": 1024, "vertical_gap": 20}

    @pytest.mark.asyncio
    async def test_update_status_preserves_chunk_options(self, pg_store):
        from src.models.documents import DocumentRecord

        doc_id = f"test_{uuid.uuid4().hex[:8]}"
        await pg_store.save_document(
            DocumentRecord(
                doc_id=doc_id,
                filename="test.pdf",
                raw_file_url=f"raw-docs/{doc_id}/test.pdf",
            )
        )
        opts = {"strategy": "heading", "max_size": 2048}
        await pg_store.update_status(doc_id, "processing", chunk_options=opts)

        # 后续状态更新不传 chunk_options，已有值应保留
        await pg_store.update_status(doc_id, "done")

        result = await pg_store.get_document(doc_id)
        assert result.status == "done"
        assert result.chunk_options == {"strategy": "heading", "max_size": 2048}

    @pytest.mark.asyncio
    async def test_save_chunk(self, pg_store):
        from src.models.documents import ChunkRecord

        doc_id = f"test_{uuid.uuid4().hex[:8]}"
        from src.models.documents import DocumentRecord

        await pg_store.save_document(
            DocumentRecord(
                doc_id=doc_id,
                filename="test.pdf",
                raw_file_url=f"raw-docs/{doc_id}/test.pdf",
            )
        )

        chunk = ChunkRecord(
            chunk_id=f"{doc_id}_p1_c0",
            doc_id=doc_id,
            chunk_type="text",
            full_text="测试内容",
            elements=[{"type": "text", "content": "测试内容", "image_url": None}],
            image_urls=[],
            page=1,
            chunk_index=0,
            char_count=4,
        )
        await pg_store.save_chunk(chunk)

    @pytest.mark.asyncio
    async def test_delete_chunks_by_doc(self, pg_store):
        from src.models.documents import ChunkRecord, DocumentRecord

        doc_id = f"test_{uuid.uuid4().hex[:8]}"
        await pg_store.save_document(
            DocumentRecord(
                doc_id=doc_id,
                filename="test.pdf",
                raw_file_url=f"raw-docs/{doc_id}/test.pdf",
            )
        )

        chunk = ChunkRecord(
            chunk_id=f"{doc_id}_p1_c0",
            doc_id=doc_id,
            chunk_type="text",
            full_text="测试内容",
            elements=[],
            image_urls=[],
            page=1,
            chunk_index=0,
            char_count=4,
        )
        await pg_store.save_chunk(chunk)
        deleted = await pg_store.delete_chunks_by_doc(doc_id)
        assert deleted == 1


class TestDatasetPgIntegration:
    """数据集 PostgreSQL 集成测试"""

    @pytest.fixture
    def pg_store(self):
        from src.storage.pg_store import PgStore

        return PgStore()

    @pytest.mark.asyncio
    async def test_create_and_get_dataset(self, pg_store):
        dataset_id = f"ds_{uuid.uuid4().hex[:8]}"
        record = await pg_store.create_dataset(
            dataset_id=dataset_id,
            name=f"测试数据集_{dataset_id}",
            description="测试描述",
        )
        assert record.dataset_id == dataset_id
        assert record.name.startswith("测试数据集_")

        fetched = await pg_store.get_dataset(dataset_id)
        assert fetched is not None
        assert fetched.name == record.name
        assert fetched.description == "测试描述"

    @pytest.mark.asyncio
    async def test_list_datasets(self, pg_store):
        dataset_id = f"ds_{uuid.uuid4().hex[:8]}"
        await pg_store.create_dataset(
            dataset_id=dataset_id,
            name=f"列表测试_{dataset_id}",
        )
        records, total = await pg_store.list_datasets(page=1, size=10)
        assert total >= 1
        assert any(r.dataset_id == dataset_id for r in records)

    @pytest.mark.asyncio
    async def test_update_dataset(self, pg_store):
        dataset_id = f"ds_{uuid.uuid4().hex[:8]}"
        await pg_store.create_dataset(
            dataset_id=dataset_id,
            name=f"更新前_{dataset_id}",
        )
        updated = await pg_store.update_dataset(
            dataset_id=dataset_id,
            name=f"更新后_{dataset_id}",
            description="新描述",
        )
        assert updated is not None
        assert updated.name == f"更新后_{dataset_id}"
        assert updated.description == "新描述"

    @pytest.mark.asyncio
    async def test_delete_dataset(self, pg_store):
        dataset_id = f"ds_{uuid.uuid4().hex[:8]}"
        await pg_store.create_dataset(
            dataset_id=dataset_id,
            name=f"删除测试_{dataset_id}",
        )
        result = await pg_store.delete_dataset(dataset_id)
        assert result is True

        fetched = await pg_store.get_dataset(dataset_id)
        assert fetched is None

    @pytest.mark.asyncio
    async def test_count_docs_by_dataset(self, pg_store):
        from src.models.documents import DocumentRecord

        dataset_id = f"ds_{uuid.uuid4().hex[:8]}"
        await pg_store.create_dataset(
            dataset_id=dataset_id,
            name=f"计数测试_{dataset_id}",
        )
        assert await pg_store.count_docs_by_dataset(dataset_id) == 0

        doc_id = f"test_{uuid.uuid4().hex[:8]}"
        await pg_store.save_document(
            DocumentRecord(
                doc_id=doc_id,
                dataset_id=dataset_id,
                filename="test.pdf",
                raw_file_url=f"raw-docs/{doc_id}/test.pdf",
            )
        )
        assert await pg_store.count_docs_by_dataset(dataset_id) == 1

    @pytest.mark.asyncio
    async def test_get_doc_ids_by_dataset_ids(self, pg_store):
        from src.models.documents import DocumentRecord

        dataset_id = f"ds_{uuid.uuid4().hex[:8]}"
        await pg_store.create_dataset(
            dataset_id=dataset_id,
            name=f"过滤测试_{dataset_id}",
        )

        doc_id = f"test_{uuid.uuid4().hex[:8]}"
        await pg_store.save_document(
            DocumentRecord(
                doc_id=doc_id,
                dataset_id=dataset_id,
                filename="test.pdf",
                raw_file_url=f"raw-docs/{doc_id}/test.pdf",
            )
        )

        ids = await pg_store.get_doc_ids_by_dataset_ids([dataset_id])
        assert doc_id in ids

    @pytest.mark.asyncio
    async def test_get_doc_ids_by_filenames(self, pg_store):
        from src.models.documents import DocumentRecord

        doc_id = f"test_{uuid.uuid4().hex[:8]}"
        unique_name = f"unique_file_{doc_id}.pdf"
        await pg_store.save_document(
            DocumentRecord(
                doc_id=doc_id,
                filename=unique_name,
                raw_file_url=f"raw-docs/{doc_id}/{unique_name}",
            )
        )

        ids = await pg_store.get_doc_ids_by_filenames([unique_name])
        assert doc_id in ids

    @pytest.mark.asyncio
    async def test_document_with_dataset_id(self, pg_store):
        from src.models.documents import DocumentRecord

        dataset_id = f"ds_{uuid.uuid4().hex[:8]}"
        await pg_store.create_dataset(
            dataset_id=dataset_id,
            name=f"关联测试_{dataset_id}",
        )

        doc_id = f"test_{uuid.uuid4().hex[:8]}"
        await pg_store.save_document(
            DocumentRecord(
                doc_id=doc_id,
                dataset_id=dataset_id,
                filename="linked.pdf",
                raw_file_url=f"raw-docs/{doc_id}/linked.pdf",
            )
        )

        fetched = await pg_store.get_document(doc_id)
        assert fetched is not None
        assert fetched.dataset_id == dataset_id

    @pytest.mark.asyncio
    async def test_delete_document(self, pg_store):
        from src.models.documents import DocumentRecord

        doc_id = f"test_{uuid.uuid4().hex[:8]}"
        await pg_store.save_document(
            DocumentRecord(
                doc_id=doc_id,
                filename="delete_me.pdf",
                raw_file_url=f"raw-docs/{doc_id}/delete_me.pdf",
            )
        )

        result = await pg_store.delete_document(doc_id)
        assert result is True

        fetched = await pg_store.get_document(doc_id)
        assert fetched is None

    @pytest.mark.asyncio
    async def test_delete_document_not_found(self, pg_store):
        result = await pg_store.delete_document("nonexistent_doc")
        assert result is False


# ---- MinIO 集成测试 ----


class TestMinIOIntegration:
    """MinIO 对象存储集成测试"""

    @pytest.fixture
    def oss_store(self):
        from src.storage.oss_store import OSSStore

        store = OSSStore()
        store.ensure_bucket()
        return store

    def test_ensure_bucket(self, oss_store):
        # 不抛异常即成功
        oss_store.ensure_bucket()

    def test_upload_and_download(self, oss_store):
        content = b"test file content"
        path = oss_store.upload_raw_doc("test_doc", "test.txt", content)
        assert path == "raw-docs/test_doc/test.txt"

        downloaded = oss_store.download(path)
        assert downloaded == content

    def test_sign_url(self, oss_store):
        content = b"test"
        path = oss_store.upload_raw_doc("test_doc", "sign_test.txt", content)
        url = oss_store.sign_url(path, expire_seconds=60)
        assert "X-Amz-Signature" in url or "signature" in url.lower() or len(url) > 50

    def test_delete(self, oss_store):
        content = b"delete me"
        path = oss_store.upload_raw_doc("test_doc", "delete_test.txt", content)
        oss_store.delete(path)
        # 删除后再下载应失败
        with pytest.raises(Exception):  # noqa: B017
            oss_store.download(path)


# ---- Milvus 集成测试 ----


class TestMilvusIntegration:
    """Milvus 向量数据库集成测试"""

    @pytest.fixture
    def milvus_store(self):
        from src.storage.milvus_store import MilvusStore

        store = MilvusStore()
        store.init_collection()
        return store

    def test_init_collection(self, milvus_store):
        # 不抛异常即成功
        pass

    def test_insert_and_search(self, milvus_store):
        import json

        doc_id = f"test_{uuid.uuid4().hex[:8]}"
        embedding = [0.1] * 1024

        record = {
            "embedding": embedding,
            "chunk_id": f"{doc_id}_p1_c0",
            "doc_id": doc_id,
            "full_text": "测试文本用于向量检索",
            "chunk_type": "text",
            "elements": json.dumps([{"type": "text", "content": "测试文本", "image_url": None}], ensure_ascii=False),
            "image_urls": "[]",
            "source": "test.pdf",
            "page": 1,
            "chunk_index": 0,
            "char_count": 10,
            "created_at": "2024-01-01T00:00:00Z",
        }
        ids = milvus_store.insert([record])
        assert len(ids) > 0

        # 搜索
        results = milvus_store.search(embedding, top_k=5)
        assert len(results) > 0
        assert results[0]["doc_id"] == doc_id

        # 清理
        milvus_store.delete_by_doc_id(doc_id)


# ---- Embedder 集成测试 ----


class TestEmbedderIntegration:
    """DashScope Embedding API 集成测试"""

    def test_embed_single(self):
        from src.ingestion.embedder import Embedder

        embedder = Embedder()
        vector = embedder.embed_single("测试文本")
        assert len(vector) == 1024
        assert any(v != 0 for v in vector)

    def test_embed_batch(self):
        from src.ingestion.embedder import Embedder

        embedder = Embedder()
        vectors = embedder.embed(["测试文本1", "测试文本2"])
        assert len(vectors) == 2
        assert len(vectors[0]) == 1024
        assert len(vectors[1]) == 1024


# ---- LLM 集成测试 ----


class TestLLMIntegration:
    """DashScope LLM API 集成测试"""

    def test_complete(self):
        from src.orchestration.llm_client import QwenClient

        client = QwenClient()
        messages = [
            {"role": "system", "content": "你是一个测试助手，请简短回答。"},
            {"role": "user", "content": "1+1等于几？只回答数字。"},
        ]
        answer = client.complete(messages)
        assert len(answer) > 0
        assert "2" in answer
