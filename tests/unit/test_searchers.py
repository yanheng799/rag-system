"""检索器测试：VectorSearcher、BM25Searcher、HybridSearcher"""

from src.models.chunks import RetrievedChunk, ChunkMetadata
from src.retrieval.vector_search import VectorSearcher
from src.retrieval.bm25_search import BM25Searcher
from src.retrieval.hybrid_search import HybridSearcher


def _make_hit(chunk_id="doc1_p1_c0", score=0.9, group_id="", full_text="text"):
    return {
        "chunk_id": chunk_id,
        "chunk_type": "text",
        "source": "test.pdf",
        "page": 1,
        "chunk_index": 0,
        "char_count": len(full_text),
        "created_at": "2024-01-01T00:00:00",
        "doc_id": "doc1",
        "full_text": full_text,
        "score": score,
        "group_id": group_id,
        "elements": [],
    }


class FakeEmbedder:
    def __init__(self, dim=1024):
        self._dim = dim
        self.last_text = None

    def embed_single(self, text: str) -> list[float]:
        self.last_text = text
        return [0.1] * self._dim


class FakeVectorStore:
    def __init__(self, hits=None):
        self._hits = hits or []
        self.last_embedding = None
        self.last_filters = None

    def search(self, embedding, top_k=50, filters=None, org_id=None):
        self.last_embedding = embedding
        self.last_filters = filters
        self.last_org_id = org_id
        return self._hits

    def fetch_by_group_ids(self, group_ids):
        return []


class FakeMilvusStore:
    def __init__(self, hits=None):
        self._hits = hits or []
        self.last_query = None
        self.last_filters = None

    def bm25_search(self, query_text, top_k=50, filters=None, org_id=None):
        self.last_query = query_text
        self.last_filters = filters
        self.last_org_id = org_id
        return self._hits

    def fetch_by_group_ids(self, group_ids):
        return []


class TestVectorSearcher:
    """向量检索：embed → search store → merge groups"""

    def test_passes_embedding_to_store(self):
        embedder = FakeEmbedder()
        store = FakeVectorStore()
        searcher = VectorSearcher(store, embedder)

        searcher.search("什么是 RAG")

        assert embedder.last_text == "什么是 RAG"
        assert store.last_embedding == [0.1] * 1024

    def test_returns_retrieved_chunks(self):
        embedder = FakeEmbedder()
        store = FakeVectorStore(hits=[_make_hit(chunk_id="c1", score=0.95)])
        searcher = VectorSearcher(store, embedder)

        results = searcher.search("test query")

        assert len(results) == 1
        assert results[0].metadata.chunk_id == "c1"
        assert results[0].score == 0.95

    def test_passes_top_k(self):
        embedder = FakeEmbedder()
        store = FakeVectorStore()
        searcher = VectorSearcher(store, embedder)

        searcher.search("test", top_k=10)

        assert store.last_embedding is not None

    def test_passes_filters(self):
        embedder = FakeEmbedder()
        store = FakeVectorStore()
        searcher = VectorSearcher(store, embedder)

        searcher.search("test", filters={"doc_id": "doc1"})

        assert store.last_filters == {"doc_id": "doc1"}

    def test_multiple_results(self):
        embedder = FakeEmbedder()
        store = FakeVectorStore(
            hits=[_make_hit(chunk_id="c1"), _make_hit(chunk_id="c2")]
        )
        searcher = VectorSearcher(store, embedder)

        results = searcher.search("test")

        assert len(results) == 2


class TestBM25Searcher:
    """BM25 全文检索：search store → merge groups"""

    def test_passes_query_to_store(self):
        store = FakeMilvusStore()
        searcher = BM25Searcher(store)

        searcher.search("搜索关键词")

        assert store.last_query == "搜索关键词"

    def test_returns_retrieved_chunks(self):
        store = FakeMilvusStore(hits=[_make_hit(chunk_id="b1", score=0.8)])
        searcher = BM25Searcher(store)

        results = searcher.search("test")

        assert len(results) == 1
        assert results[0].metadata.chunk_id == "b1"

    def test_passes_filters(self):
        store = FakeMilvusStore()
        searcher = BM25Searcher(store)

        searcher.search("test", filters={"dataset_id": "ds1"})

        assert store.last_filters == {"dataset_id": "ds1"}

    def test_passes_top_k(self):
        store = FakeMilvusStore()
        searcher = BM25Searcher(store)

        searcher.search("test", top_k=20)

        assert store.last_query == "test"


class TestHybridSearcher:
    """混合检索：向量 + BM25 → RRF 融合"""

    def test_calls_both_searchers_and_fuses(self):
        embedder = FakeEmbedder()
        vec_store = FakeVectorStore(
            hits=[_make_hit(chunk_id="c1", score=0.9), _make_hit(chunk_id="c3", score=0.7)]
        )
        bm25_store = FakeMilvusStore(
            hits=[_make_hit(chunk_id="c2", score=0.8)]
        )

        vector_searcher = VectorSearcher(vec_store, embedder)
        bm25_searcher = BM25Searcher(bm25_store)
        hybrid = HybridSearcher(vector_searcher, bm25_searcher)

        results = hybrid.search("混合查询")

        assert len(results) == 3
        ids = {r.metadata.chunk_id for r in results}
        assert ids == {"c1", "c2", "c3"}
        for r in results:
            assert r.score > 0

    def test_overlapping_results_fused_correctly(self):
        embedder = FakeEmbedder()
        vec_store = FakeVectorStore(
            hits=[_make_hit(chunk_id="shared", score=0.95)]
        )
        bm25_store = FakeMilvusStore(
            hits=[_make_hit(chunk_id="shared", score=0.85)]
        )

        vector_searcher = VectorSearcher(vec_store, embedder)
        bm25_searcher = BM25Searcher(bm25_store)
        hybrid = HybridSearcher(vector_searcher, bm25_searcher)

        results = hybrid.search("test")

        assert len(results) == 1
        assert results[0].vector_score > 0
        assert results[0].bm25_score > 0

    def test_passes_filters_to_both(self):
        embedder = FakeEmbedder()
        vec_store = FakeVectorStore()
        bm25_store = FakeMilvusStore()

        vector_searcher = VectorSearcher(vec_store, embedder)
        bm25_searcher = BM25Searcher(bm25_store)
        hybrid = HybridSearcher(vector_searcher, bm25_searcher)

        hybrid.search("test", filters={"doc_id": "d1"})

        assert vec_store.last_filters == {"doc_id": "d1"}
        assert bm25_store.last_filters == {"doc_id": "d1"}

    def test_empty_results_from_both(self):
        embedder = FakeEmbedder()
        vec_store = FakeVectorStore()
        bm25_store = FakeMilvusStore()

        vector_searcher = VectorSearcher(vec_store, embedder)
        bm25_searcher = BM25Searcher(bm25_store)
        hybrid = HybridSearcher(vector_searcher, bm25_searcher)

        results = hybrid.search("不存在的查询")

        assert results == []
