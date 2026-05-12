"""共享数据模型测试"""

import pytest

from models.chunks import (
    ChunkMetadata,
    ContentElement,
    MixedChunk,
    RetrievedChunk,
)
from models.documents import ChunkRecord, DatasetRecord, DocumentRecord


class TestContentElement:
    def test_text_element(self):
        elem = ContentElement(type="text", content="Hello")
        assert elem.image_url is None
        assert elem.type == "text"

    def test_table_element(self):
        elem = ContentElement(type="table", content="表格内容", image_url="/path/img.png")
        assert elem.image_url == "/path/img.png"
        assert elem.type == "table"

    def test_serialization(self):
        elem = ContentElement(type="text", content="测试")
        d = elem.to_dict()
        restored = ContentElement.from_dict(d)
        assert restored.type == elem.type
        assert restored.content == elem.content


class TestChunkMetadata:
    def test_metadata_creation(self):
        meta = ChunkMetadata(
            chunk_id="doc_001_p1_c0",
            chunk_type="text",
            source="test.pdf",
            page=1,
            chunk_index=0,
            char_count=100,
            created_at="2024-01-01T00:00:00Z",
            doc_id="doc_001",
        )
        assert meta.chunk_id == "doc_001_p1_c0"

    def test_serialization(self):
        meta = ChunkMetadata(
            chunk_id="doc_001_p1_c0",
            chunk_type="text",
            source="test.pdf",
            page=1,
            chunk_index=0,
            char_count=100,
            created_at="2024-01-01T00:00:00Z",
            doc_id="doc_001",
        )
        d = meta.to_dict()
        restored = ChunkMetadata.from_dict(d)
        assert restored.chunk_id == meta.chunk_id


class TestMixedChunk:
    def test_mixed_chunk(self):
        elements = [
            ContentElement(type="text", content="说明文字"),
            ContentElement(type="table", content="表格描述", image_url="/img.png"),
        ]
        meta = ChunkMetadata(
            chunk_id="doc_001_p1_c0",
            chunk_type="mixed",
            source="test.pdf",
            page=1,
            chunk_index=0,
            char_count=50,
            created_at="2024-01-01T00:00:00Z",
            doc_id="doc_001",
        )
        chunk = MixedChunk(
            metadata=meta,
            elements=elements,
            full_text="说明文字\n表格描述",
            image_urls=["/img.png"],
        )
        assert len(chunk.elements) == 2
        assert chunk.full_text == "说明文字\n表格描述"


class TestRetrievedChunk:
    def test_retrieved_chunk(self):
        meta = ChunkMetadata(
            chunk_id="doc_001_p1_c0",
            chunk_type="text",
            source="test.pdf",
            page=1,
            chunk_index=0,
            char_count=50,
            created_at="2024-01-01T00:00:00Z",
            doc_id="doc_001",
        )
        chunk = RetrievedChunk(
            metadata=meta,
            elements=[ContentElement(type="text", content="内容")],
            full_text="内容",
            score=0.95,
        )
        assert chunk.score == 0.95


class TestDocumentRecord:
    def test_document_record(self):
        doc = DocumentRecord(
            doc_id="doc_001",
            filename="test.pdf",
            raw_file_url="raw-docs/doc_001/test.pdf",
            file_type="pdf",
        )
        assert doc.status == "pending"
        assert doc.retry_count == 0
        assert doc.dataset_id is None

    def test_document_record_with_dataset(self):
        doc = DocumentRecord(
            doc_id="doc_002",
            filename="test.docx",
            raw_file_url="raw-docs/doc_002/test.docx",
            dataset_id="ds_abc123",
        )
        assert doc.dataset_id == "ds_abc123"


class TestDatasetRecord:
    def test_dataset_record(self):
        ds = DatasetRecord(
            dataset_id="ds_abc123",
            name="测试数据集",
        )
        assert ds.dataset_id == "ds_abc123"
        assert ds.name == "测试数据集"
        assert ds.description is None
        assert ds.created_by is None

    def test_dataset_record_full(self):
        from datetime import datetime

        now = datetime(2024, 1, 1, 12, 0, 0)
        ds = DatasetRecord(
            dataset_id="ds_abc123",
            name="电力工程",
            description="输电线路数据",
            created_by="user_001",
            created_at=now,
            updated_at=now,
        )
        assert ds.description == "输电线路数据"
        assert ds.created_by == "user_001"
