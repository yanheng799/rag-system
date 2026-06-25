"""Prompt 构建器测试"""

from src.models.chunks import (
    ChunkMetadata,
    ContentElement,
    RetrievedChunk,
)
from src.orchestration.prompt_builder import PromptBuilder


class TestPromptBuilder:
    def setup_method(self):
        self.builder = PromptBuilder()

    def _make_chunk(self, source: str, page: int, content: str) -> RetrievedChunk:
        meta = ChunkMetadata(
            chunk_id=f"doc_001_p{page}_c0",
            chunk_type="text",
            source=source,
            page=page,
            chunk_index=0,
            char_count=len(content),
            created_at="2024-01-01T00:00:00Z",
            doc_id="doc_001",
        )
        return RetrievedChunk(
            metadata=meta,
            elements=[ContentElement(type="text", content=content)],
            full_text=content,
            score=0.9,
        )

    def test_build_basic_prompt(self):
        chunks = [
            self._make_chunk("报告.pdf", 3, "华东区Q1完成120万"),
            self._make_chunk("报告.pdf", 4, "Q2下降原因分析"),
        ]
        messages = self.builder.build("华东区情况如何？", chunks)

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "华东区情况如何？" in messages[1]["content"]
        assert "参考资料1" in messages[1]["content"]
        assert "参考资料2" in messages[1]["content"]
        assert "报告.pdf" in messages[1]["content"]

    def test_build_with_empty_chunks(self):
        messages = self.builder.build("问题", [])
        assert len(messages) == 2
        assert "问题" in messages[1]["content"]

    def test_image_url_not_in_prompt(self):
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
        chunk = RetrievedChunk(
            metadata=meta,
            elements=[
                ContentElement(type="text", content="说明文字"),
                ContentElement(
                    type="table",
                    content="表格描述",
                    image_url="/path/to/image.png",
                ),
            ],
            full_text="说明文字\n表格描述",
            image_urls=["/path/to/image.png"],
            score=0.85,
        )
        messages = self.builder.build("问题", [chunk])
        user_msg = messages[1]["content"]
        assert "/path/to/image.png" not in user_msg
        assert "表格描述" in user_msg
