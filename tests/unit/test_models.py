"""共享数据模型测试 — 序列化往返、默认值、边界"""

from datetime import datetime

from src.models.chunks import (
    ChunkMetadata,
    ContentElement,
    MixedChunk,
    RetrievedChunk,
)
from src.models.documents import ChunkRecord, DatasetRecord, DocumentRecord, QueryLogRecord


def _make_meta(**overrides) -> ChunkMetadata:
    defaults = dict(
        chunk_id="doc_001_p1_c0",
        chunk_type="text",
        source="test.pdf",
        page=1,
        chunk_index=0,
        char_count=100,
        created_at="2024-01-01T00:00:00Z",
        doc_id="doc_001",
    )
    return ChunkMetadata(**{**defaults, **overrides})


# ---- ContentElement ----


class TestContentElement:
    def test_text_element_no_image_url(self):
        elem = ContentElement(type="text", content="Hello")
        assert elem.image_url is None

    def test_table_element_has_image_url(self):
        elem = ContentElement(type="table", content="表格内容", image_url="/path/img.png")
        assert elem.image_url == "/path/img.png"

    def test_roundtrip_with_image_url(self):
        elem = ContentElement(type="table", content="表格", image_url="img.png")
        restored = ContentElement.from_dict(elem.to_dict())
        assert restored.type == elem.type
        assert restored.content == elem.content
        assert restored.image_url == "img.png"

    def test_from_dict_without_optional_key(self):
        data = {"type": "text", "content": "hello"}
        elem = ContentElement.from_dict(data)
        assert elem.image_url is None

    def test_empty_content(self):
        elem = ContentElement(type="text", content="")
        assert elem.content == ""
        assert ContentElement.from_dict(elem.to_dict()).content == ""


# ---- ChunkMetadata ----


class TestChunkMetadata:
    def test_creation(self):
        meta = _make_meta()
        assert meta.chunk_id == "doc_001_p1_c0"
        assert meta.pages == []
        assert meta.group_id == ""

    def test_roundtrip_preserves_all_fields(self):
        meta = _make_meta(pages=[1, 2], group_id="doc_001_g0")
        restored = ChunkMetadata.from_dict(meta.to_dict())
        assert restored.pages == [1, 2]
        assert restored.group_id == "doc_001_g0"
        assert restored.chunk_id == meta.chunk_id
        assert restored.doc_id == meta.doc_id

    def test_from_dict_missing_optional_fields(self):
        data = {
            "chunk_id": "c1", "chunk_type": "text", "source": "f.pdf",
            "page": 1, "chunk_index": 0, "char_count": 10,
            "created_at": "2024-01-01", "doc_id": "d1",
        }
        meta = ChunkMetadata.from_dict(data)
        assert meta.pages == []
        assert meta.group_id == ""

    def test_pages_default_factory_independent(self):
        """两个实例的 pages 列表互不影响"""
        m1 = _make_meta()
        m2 = _make_meta()
        m1.pages.append(99)
        assert m2.pages == []


# ---- MixedChunk ----


class TestMixedChunk:
    def test_creation_with_elements(self):
        elements = [
            ContentElement(type="text", content="说明文字"),
            ContentElement(type="table", content="表格描述", image_url="/img.png"),
        ]
        meta = _make_meta(chunk_type="mixed")
        chunk = MixedChunk(metadata=meta, elements=elements, full_text="说明文字\n表格描述", image_urls=["/img.png"])
        assert len(chunk.elements) == 2
        assert chunk.full_text == "说明文字\n表格描述"

    def test_to_dict_nested_serialization(self):
        elements = [ContentElement(type="text", content="hello")]
        meta = _make_meta()
        chunk = MixedChunk(metadata=meta, elements=elements, full_text="hello")

        d = chunk.to_dict()
        assert isinstance(d["metadata"], dict)
        assert isinstance(d["elements"], list)
        assert d["elements"][0]["content"] == "hello"
        assert d["full_text"] == "hello"
        assert d["image_urls"] == []

    def test_empty_chunk(self):
        meta = _make_meta()
        chunk = MixedChunk(metadata=meta)
        assert chunk.elements == []
        assert chunk.full_text == ""
        assert chunk.image_urls == []


# ---- RetrievedChunk ----


class TestRetrievedChunk:
    def test_creation_with_score(self):
        meta = _make_meta()
        chunk = RetrievedChunk(metadata=meta, full_text="内容", score=0.95)
        assert chunk.score == 0.95

    def test_default_scores(self):
        meta = _make_meta()
        chunk = RetrievedChunk(metadata=meta)
        assert chunk.score == 0.0
        assert chunk.vector_score == 0.0
        assert chunk.bm25_score == 0.0

    def test_to_dict_includes_all_scores(self):
        meta = _make_meta()
        chunk = RetrievedChunk(metadata=meta, score=0.8, vector_score=0.7, bm25_score=0.3)
        d = chunk.to_dict()
        assert d["score"] == 0.8
        assert d["vector_score"] == 0.7
        assert d["bm25_score"] == 0.3


# ---- DocumentRecord ----


class TestDocumentRecord:
    def test_defaults(self):
        doc = DocumentRecord(doc_id="d1", filename="f.pdf", raw_file_url="raw/d1/f.pdf")
        assert doc.status == "pending"
        assert doc.retry_count == 0
        assert doc.dataset_id is None
        assert doc.content_hash is None
        assert doc.file_size is None
        assert doc.error_msg is None

    def test_with_dataset(self):
        doc = DocumentRecord(doc_id="d2", filename="f.docx", raw_file_url="raw/d2/f.docx", dataset_id="ds_abc123")
        assert doc.dataset_id == "ds_abc123"

    def test_full_creation(self):
        now = datetime(2024, 1, 1)
        doc = DocumentRecord(
            doc_id="d3", filename="f.xlsx", raw_file_url="raw/d3/f.xlsx",
            content_hash="abc123", file_size=1024, file_type="xlsx",
            status="done", uploaded_at=now, updated_at=now,
        )
        assert doc.content_hash == "abc123"
        assert doc.file_size == 1024
        assert doc.status == "done"


# ---- ChunkRecord ----


class TestChunkRecord:
    def test_defaults(self):
        rec = ChunkRecord(
            chunk_id="d1_p1_c0", doc_id="d1", chunk_type="text",
            full_text="hello", elements=[], image_urls=[], page=1, chunk_index=0, char_count=5,
        )
        assert rec.group_id == ""
        assert rec.created_at is None

    def test_with_group_id(self):
        rec = ChunkRecord(
            chunk_id="d1_p1_c0", doc_id="d1", chunk_type="text",
            full_text="hello", elements=[], image_urls=[], page=1, chunk_index=0,
            char_count=5, group_id="d1_g0",
        )
        assert rec.group_id == "d1_g0"


# ---- DatasetRecord ----


class TestDatasetRecord:
    def test_minimal(self):
        ds = DatasetRecord(dataset_id="ds1", name="测试")
        assert ds.description is None
        assert ds.created_by is None

    def test_full(self):
        now = datetime(2024, 1, 1, 12, 0, 0)
        ds = DatasetRecord(
            dataset_id="ds1", name="电力工程",
            description="输电线路数据", created_by="user_001",
            created_at=now, updated_at=now,
        )
        assert ds.description == "输电线路数据"
        assert ds.created_by == "user_001"


# ---- QueryLogRecord ----


class TestQueryLogRecord:
    def test_defaults(self):
        rec = QueryLogRecord(log_id="q1", question="什么是RAG？")
        assert rec.answer is None
        assert rec.retrieved_chunks is None
        assert rec.cache_hit is False
        assert rec.token_count is None
