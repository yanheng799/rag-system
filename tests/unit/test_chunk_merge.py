"""分块合并工具测试"""

from src.models.chunks import RetrievedChunk
from src.retrieval.chunk_merge import hit_to_chunk, merge_grouped_chunks


def _make_hit(
    chunk_id: str = "doc1_p1_c0",
    score: float = 0.9,
    group_id: str = "",
    page: int = 1,
    chunk_index: int = 0,
    full_text: str = "sample text",
    elements: list[dict] | None = None,
) -> dict:
    return {
        "chunk_id": chunk_id,
        "chunk_type": "text",
        "source": "test.pdf",
        "page": page,
        "chunk_index": chunk_index,
        "char_count": len(full_text),
        "created_at": "2024-01-01T00:00:00",
        "doc_id": "doc1",
        "full_text": full_text,
        "score": score,
        "group_id": group_id,
        "elements": elements or [],
    }


class TestHitToChunk:
    """Milvus 命中记录转为 RetrievedChunk"""

    def test_basic_field_mapping(self):
        hit = _make_hit(chunk_id="doc1_p2_c3", score=0.88)

        chunk = hit_to_chunk(hit)

        assert chunk.metadata.chunk_id == "doc1_p2_c3"
        assert chunk.score == 0.88
        assert chunk.full_text == "sample text"
        assert chunk.metadata.page == 1
        assert chunk.metadata.chunk_index == 0

    def test_elements_parsed(self):
        hit = _make_hit(
            elements=[
                {"type": "text", "content": "hello"},
                {"type": "table", "content": "| a | b |", "image_url": "/path/img.png"},
            ]
        )

        chunk = hit_to_chunk(hit)

        assert len(chunk.elements) == 2
        assert chunk.elements[0].type == "text"
        assert chunk.elements[1].type == "table"
        assert chunk.elements[1].image_url == "/path/img.png"

    def test_group_id_default_empty(self):
        hit = _make_hit()

        chunk = hit_to_chunk(hit)

        assert chunk.metadata.group_id == ""

    def test_group_id_set(self):
        hit = _make_hit(group_id="grp1")

        chunk = hit_to_chunk(hit)

        assert chunk.metadata.group_id == "grp1"

    def test_pages_defaults_to_page(self):
        hit = _make_hit(page=5)

        chunk = hit_to_chunk(hit)

        assert chunk.metadata.pages == [5]

    def test_pages_explicit(self):
        hit = _make_hit(page=2)
        hit["pages"] = [2, 3]

        chunk = hit_to_chunk(hit)

        assert chunk.metadata.pages == [2, 3]

    def test_image_urls_default_empty(self):
        hit = _make_hit()

        chunk = hit_to_chunk(hit)

        assert chunk.image_urls == []


class TestMergeGroupedChunksPassthrough:
    """无 group_id 的分块直接透传"""

    def test_no_groups_returns_as_is(self):
        chunks = [
            hit_to_chunk(_make_hit(chunk_id="c1")),
            hit_to_chunk(_make_hit(chunk_id="c2")),
        ]

        result = merge_grouped_chunks(chunks, lambda ids: [])

        assert len(result) == 2
        assert result[0].metadata.chunk_id == "c1"
        assert result[1].metadata.chunk_id == "c2"


class TestMergeGroupedChunksMerge:
    """同一 group_id 的分块合并为完整段落"""

    def test_siblings_merged_text(self):
        chunks = [
            hit_to_chunk(_make_hit(chunk_id="doc1_p1_c0", group_id="g1", full_text="前半段")),
            hit_to_chunk(_make_hit(chunk_id="doc1_p1_c1", group_id="g1", full_text="后半段")),
        ]

        def fetch_fn(group_ids):
            return []

        result = merge_grouped_chunks(chunks, fetch_fn)

        assert len(result) == 1
        assert "前半段" in result[0].full_text
        assert "后半段" in result[0].full_text

    def test_merged_score_is_max(self):
        chunks = [
            hit_to_chunk(_make_hit(chunk_id="c0", group_id="g1", score=0.5)),
            hit_to_chunk(_make_hit(chunk_id="c1", group_id="g1", score=0.9)),
        ]

        result = merge_grouped_chunks(chunks, lambda ids: [])

        assert result[0].score == 0.9

    def test_fetch_supplements_missing_sibling(self):
        chunks = [
            hit_to_chunk(_make_hit(chunk_id="doc1_p1_c0", group_id="g1", full_text="第一部分")),
        ]

        def fetch_fn(group_ids):
            return [
                _make_hit(
                    chunk_id="doc1_p1_c1",
                    group_id="g1",
                    full_text="第二部分（来自 fetch）",
                    page=1,
                    chunk_index=1,
                )
            ]

        result = merge_grouped_chunks(chunks, fetch_fn)

        assert len(result) == 1
        assert "第二部分（来自 fetch）" in result[0].full_text

    def test_fetch_does_not_duplicate_existing(self):
        chunks = [
            hit_to_chunk(_make_hit(chunk_id="doc1_p1_c0", group_id="g1")),
            hit_to_chunk(_make_hit(chunk_id="doc1_p1_c1", group_id="g1")),
        ]

        def fetch_fn(group_ids):
            return [
                _make_hit(chunk_id="doc1_p1_c0", group_id="g1"),
            ]

        result = merge_grouped_chunks(chunks, fetch_fn)

        assert len(result) == 1
        texts = result[0].full_text.split("\n")
        assert len(texts) == 2

    def test_merged_pages_deduplicated(self):
        chunks = [
            hit_to_chunk(_make_hit(chunk_id="c0", group_id="g1", page=1)),
            hit_to_chunk(_make_hit(chunk_id="c1", group_id="g1", page=2)),
        ]

        result = merge_grouped_chunks(chunks, lambda ids: [])

        assert result[0].metadata.pages == [1, 2]

    def test_merged_elements_concatenated(self):
        chunks = [
            hit_to_chunk(
                _make_hit(
                    chunk_id="c0",
                    group_id="g1",
                    elements=[{"type": "text", "content": "A"}],
                )
            ),
            hit_to_chunk(
                _make_hit(
                    chunk_id="c1",
                    group_id="g1",
                    elements=[{"type": "table", "content": "B"}],
                )
            ),
        ]

        result = merge_grouped_chunks(chunks, lambda ids: [])

        assert len(result[0].elements) == 2
        assert result[0].elements[0].content == "A"
        assert result[0].elements[1].content == "B"


class TestMergeGroupedChunksFallback:
    """fetch 失败时回退到原始列表"""

    def test_fetch_exception_returns_original(self):
        chunks = [
            hit_to_chunk(_make_hit(chunk_id="c0", group_id="g1")),
        ]

        def fetch_fn(group_ids):
            raise ConnectionError("Milvus down")

        result = merge_grouped_chunks(chunks, fetch_fn)

        assert len(result) == 1
        assert result[0].metadata.chunk_id == "c0"

    def test_mixed_groups_and_singles(self):
        chunks = [
            hit_to_chunk(_make_hit(chunk_id="c0", group_id="g1", full_text="A")),
            hit_to_chunk(_make_hit(chunk_id="c1", group_id="g1", full_text="B")),
            hit_to_chunk(_make_hit(chunk_id="c2", group_id="", full_text="standalone")),
        ]

        result = merge_grouped_chunks(chunks, lambda ids: [])

        assert len(result) == 2
        merged = [c for c in result if c.metadata.group_id == "g1"]
        standalone = [c for c in result if c.metadata.chunk_id == "c2"]
        assert len(merged) == 1
        assert "A" in merged[0].full_text
        assert "B" in merged[0].full_text
        assert len(standalone) == 1
        assert standalone[0].full_text == "standalone"
