"""Milvus org_id 隔离测试 — 验证 org_id 在检索链中的传递"""

from src.models.chunks import RetrievedChunk, ChunkMetadata
from src.retrieval.vector_search import VectorSearcher
from src.retrieval.bm25_search import BM25Searcher
from src.retrieval.hybrid_search import HybridSearcher


def _make_hit(chunk_id="c1", doc_id="d1", score=0.9, group_id=""):
    return {
        "chunk_id": chunk_id,
        "chunk_type": "text",
        "source": "test.pdf",
        "page": 1,
        "chunk_index": 0,
        "char_count": 10,
        "created_at": "2024-01-01T00:00:00",
        "doc_id": doc_id,
        "full_text": "text",
        "score": score,
        "group_id": group_id,
        "elements": [],
        "pages": "[1]",
        "image_urls": "[]",
    }


class FakeEmbedder:
    def embed_single(self, text: str) -> list[float]:
        return [0.1] * 1024


class TrackedVectorStore:
    """记录 search 调用的 org_id 参数"""
    def __init__(self, hits=None):
        self._hits = hits or []
        self.last_org_id = None
        self.last_filters = None

    def search(self, embedding, top_k=50, filters=None, org_id=None):
        self.last_org_id = org_id
        self.last_filters = filters
        return self._hits

    def fetch_by_group_ids(self, group_ids):
        return []

    def bm25_search(self, query_text, top_k=50, filters=None, org_id=None):
        self.last_org_id = org_id
        self.last_filters = filters
        return self._hits


class TestVectorSearchOrgId:
    def test_org_id_passed_to_vector_store(self):
        store = TrackedVectorStore(hits=[_make_hit()])
        searcher = VectorSearcher(store, FakeEmbedder())

        searcher.search("query", org_id="org_alpha")
        assert store.last_org_id == "org_alpha"

    def test_no_org_id_passes_none(self):
        store = TrackedVectorStore(hits=[_make_hit()])
        searcher = VectorSearcher(store, FakeEmbedder())

        searcher.search("query")
        assert store.last_org_id is None

    def test_filters_and_org_id_both_passed(self):
        store = TrackedVectorStore(hits=[_make_hit()])
        searcher = VectorSearcher(store, FakeEmbedder())

        searcher.search("query", filters={"doc_id": "d1"}, org_id="org_a")
        assert store.last_filters == {"doc_id": "d1"}
        assert store.last_org_id == "org_a"


class TestBM25SearchOrgId:
    def test_org_id_passed_to_bm25_store(self):
        store = TrackedVectorStore(hits=[_make_hit()])
        searcher = BM25Searcher(store)

        searcher.search("query", org_id="org_beta")
        assert store.last_org_id == "org_beta"


class TestHybridSearchOrgId:
    def test_org_id_passed_to_both_searchers(self):
        vs = TrackedVectorStore(hits=[_make_hit("c1")])
        bm25s = TrackedVectorStore(hits=[_make_hit("c2")])
        hybrid = HybridSearcher(
            VectorSearcher(vs, FakeEmbedder()),
            BM25Searcher(bm25s),
        )

        hybrid.search("query", org_id="org_gamma")
        assert vs.last_org_id == "org_gamma"
        assert bm25s.last_org_id == "org_gamma"

    def test_hybrid_returns_merged_results(self):
        vs = TrackedVectorStore(hits=[_make_hit("c1", score=0.9)])
        bm25s = TrackedVectorStore(hits=[_make_hit("c2", score=0.5)])
        hybrid = HybridSearcher(
            VectorSearcher(vs, FakeEmbedder()),
            BM25Searcher(bm25s),
        )

        results = hybrid.search("query", org_id="org_a")
        assert len(results) >= 1


class TestMilvusExprBuilder:
    """测试 Milvus _build_expr 方法"""
    def test_build_expr_with_filters_and_org_id(self):
        from src.storage.milvus_store import MilvusStore

        store = MilvusStore()
        store._collection = type("FakeColl", (), {"schema": type("Schema", (), {"fields": [type("F", (), {"name": "org_id"})()]})()})()

        expr = store._build_expr({"doc_id": "d1"}, org_id="org_a")
        assert 'doc_id == "d1"' in expr
        assert 'org_id == "org_a"' in expr

    def test_build_expr_no_org_id_field(self):
        from src.storage.milvus_store import MilvusStore

        store = MilvusStore()
        store._collection = type("FakeColl", (), {"schema": type("Schema", (), {"fields": []})()})()

        expr = store._build_expr(filters=None, org_id="org_a")
        assert expr is None  # no org_id field, so org_id filter not added

    def test_build_expr_filters_only(self):
        from src.storage.milvus_store import MilvusStore

        store = MilvusStore()
        store._collection = type("FakeColl", (), {"schema": type("Schema", (), {"fields": [type("F", (), {"name": "org_id"})()]})()})()

        expr = store._build_expr({"doc_id": ["d1", "d2"]})
        assert 'doc_id in [' in expr

    def test_build_expr_none_when_empty(self):
        from src.storage.milvus_store import MilvusStore

        store = MilvusStore()
        store._collection = type("FakeColl", (), {"schema": type("Schema", (), {"fields": [type("F", (), {"name": "org_id"})()]})()})()

        expr = store._build_expr(filters=None, org_id=None)
        assert expr is None
