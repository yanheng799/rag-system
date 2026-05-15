"""RRF 融合算法测试"""

from src.models.chunks import ChunkMetadata, RetrievedChunk
from src.retrieval.rrf_fusion import rrf_fuse


def _make_chunk(chunk_id: str, score: float = 0.0) -> RetrievedChunk:
    return RetrievedChunk(
        metadata=ChunkMetadata(
            chunk_id=chunk_id,
            chunk_type="text",
            source="test.pdf",
            page=1,
            chunk_index=0,
            char_count=100,
            created_at="2024-01-01T00:00:00",
            doc_id="doc1",
        ),
        full_text="test content",
        score=score,
    )


class TestRRFScoreCalculation:
    """RRF 分数计算：score(d) = 1/(k + rank_vector) + 1/(k + rank_bm25)"""

    def test_single_list_returns_correct_score(self):
        chunk = _make_chunk("c1", score=0.9)
        result = rrf_fuse([chunk], [], rrf_k=60)

        assert len(result) == 1
        assert result[0].score == 1.0 / (60 + 1)

    def test_chunk_in_both_lists_gets_higher_score(self):
        chunk_a = _make_chunk("c1", score=0.9)
        chunk_b = _make_chunk("c1", score=0.8)

        result = rrf_fuse([chunk_a], [chunk_b], rrf_k=60)

        assert len(result) == 1
        expected = 1.0 / (60 + 1) + 1.0 / (60 + 1)
        assert abs(result[0].score - expected) < 1e-9

    def test_scores_preserved_on_chunk(self):
        v_chunk = _make_chunk("c1", score=0.95)
        b_chunk = _make_chunk("c1", score=0.75)

        result = rrf_fuse([v_chunk], [b_chunk], rrf_k=60)

        assert result[0].vector_score == 0.95
        assert result[0].bm25_score == 0.75


class TestRRFOrdering:
    """融合结果按 RRF 分数降序排列"""

    def test_sorted_descending(self):
        chunks_v = [_make_chunk("c1"), _make_chunk("c2"), _make_chunk("c3")]
        chunks_b = [_make_chunk("c3"), _make_chunk("c1"), _make_chunk("c4")]

        result = rrf_fuse(chunks_v, chunks_b, rrf_k=60)

        for i in range(len(result) - 1):
            assert result[i].score >= result[i + 1].score

    def test_chunk_appearing_in_both_ranks_highest(self):
        v_only = _make_chunk("v_only")
        both = _make_chunk("both")
        b_only = _make_chunk("b_only")

        result = rrf_fuse([v_only, both], [both, b_only], rrf_k=60)

        assert result[0].metadata.chunk_id == "both"


class TestRRFDedup:
    """同一 chunk_id 在两路结果中不重复"""

    def test_no_duplicates_in_result(self):
        chunks_v = [_make_chunk("c1"), _make_chunk("c2")]
        chunks_b = [_make_chunk("c2"), _make_chunk("c1")]

        result = rrf_fuse(chunks_v, chunks_b, rrf_k=60)

        ids = [c.metadata.chunk_id for c in result]
        assert len(ids) == len(set(ids))

    def test_vector_only_chunks_included(self):
        result = rrf_fuse([_make_chunk("c1", score=0.9)], [], rrf_k=60)

        assert len(result) == 1
        assert result[0].metadata.chunk_id == "c1"
        assert result[0].vector_score == 0.9

    def test_bm25_only_chunks_included(self):
        result = rrf_fuse([], [_make_chunk("c1", score=0.8)], rrf_k=60)

        assert len(result) == 1
        assert result[0].metadata.chunk_id == "c1"
        assert result[0].bm25_score == 0.8

    def test_empty_both_lists(self):
        result = rrf_fuse([], [], rrf_k=60)
        assert result == []


class TestRRFKParameter:
    """rrf_k 参数可覆盖"""

    def test_custom_k_affects_score(self):
        r1 = rrf_fuse([_make_chunk("c1", score=0.9)], [], rrf_k=60)
        r2 = rrf_fuse([_make_chunk("c1", score=0.9)], [], rrf_k=10)

        assert r1[0].score != r2[0].score
        assert r2[0].score > r1[0].score

    def test_smaller_k_means_larger_score(self):
        result_k10 = rrf_fuse([_make_chunk("c1")], [], rrf_k=10)
        result_k100 = rrf_fuse([_make_chunk("c1")], [], rrf_k=100)

        assert result_k10[0].score > result_k100[0].score
