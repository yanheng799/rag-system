"""Retrieve API Reranker 集成测试"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.retrieve import router
from src.config.settings import settings
from src.models.chunks import ChunkMetadata, RetrievedChunk
from src.retrieval.reranker import RerankResult


def _make_chunk(chunk_id: str, full_text: str = "内容", score: float = 0.9) -> RetrievedChunk:
    return RetrievedChunk(
        metadata=ChunkMetadata(
            chunk_id=chunk_id,
            chunk_type="text",
            source="test.pdf",
            page=1,
            chunk_index=0,
            char_count=len(full_text),
            created_at="2024-01-01T00:00:00",
            doc_id="doc1",
        ),
        elements=[],
        full_text=full_text,
        score=score,
    )


def _fake_doc(filename: str = "test.pdf") -> MagicMock:
    doc = MagicMock()
    doc.filename = filename
    return doc


def _make_app(reranker_client=None, searcher=None):
    app = FastAPI()
    app.state.reranker_client = reranker_client
    app.state.hybrid_searcher = searcher or MagicMock()
    app.state.vector_searcher = searcher or MagicMock()
    app.state.bm25_searcher = searcher or MagicMock()
    pg_store = MagicMock()
    pg_store.get_document = AsyncMock(return_value=_fake_doc())
    app.state.pg_store = pg_store
    app.state.query_rewriter = None
    app.include_router(router)
    return TestClient(app)


class TestRetrieveRerankerNotConfigured:
    """use_reranker=true 但未配置 reranker → 返回 503"""

    def test_reranker_not_configured_returns_503(self):
        # reranker_client=None 模拟未配置
        client = _make_app(reranker_client=None)
        with patch.object(settings, "auth_enabled", False):
            resp = client.post("/api/v1/retrieve", json={
                "question": "测试",
                "top_k": 5,
                "use_reranker": True,
            })
        assert resp.status_code == 503
        assert "Reranker 服务未配置" in resp.json()["detail"]


class TestRetrieveRerankerNormal:
    """use_reranker=true 正常流程 → 结果包含 rerank_score，数量 ≤ rerank_top_n"""

    def test_reranker_reorders_and_truncates(self):
        # 搜索返回 6 条（top_k=2, multiplier=3 → fetch 6）
        fake_results = [
            _make_chunk("c1", full_text="文档A", score=0.9),
            _make_chunk("c2", full_text="文档B", score=0.8),
            _make_chunk("c3", full_text="文档C", score=0.7),
            _make_chunk("c4", full_text="文档D", score=0.6),
            _make_chunk("c5", full_text="文档E", score=0.5),
            _make_chunk("c6", full_text="文档F", score=0.4),
        ]

        fake_searcher = MagicMock()
        fake_searcher.search.return_value = fake_results

        # Reranker 把 c3 排第一，c1 排第二（和原始顺序不同）
        fake_reranker = MagicMock()
        fake_reranker.rerank.return_value = [
            RerankResult(index=2, relevance_score=0.95),
            RerankResult(index=0, relevance_score=0.88),
        ]

        # 模拟 pg_store.get_document 返回文件名
        fake_doc = MagicMock()
        fake_doc.filename = "test.pdf"

        client = _make_app(reranker_client=fake_reranker, searcher=fake_searcher)
        with patch.object(settings, "auth_enabled", False), \
             patch.object(settings, "rerank_fetch_multiplier", 3):
            resp = client.post("/api/v1/retrieve", json={
                "question": "测试",
                "top_k": 2,
                "use_reranker": True,
                "rerank_top_n": 2,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_retrieved"] == 2
        # c3 排第一
        assert data["chunks"][0]["metadata"]["chunk_id"] == "c3"
        assert data["chunks"][0]["scores"]["rerank_score"] == 0.95
        # c1 排第二
        assert data["chunks"][1]["metadata"]["chunk_id"] == "c1"
        assert data["chunks"][1]["scores"]["rerank_score"] == 0.88
        # rrf_score 保留原始检索分数
        assert data["chunks"][0]["scores"]["rrf_score"] is not None


class TestRetrieveRerankerDisabled:
    """use_reranker=false（默认）→ rerank_score 为 None"""

    def test_no_reranker_by_default(self):
        fake_results = [_make_chunk("c1", full_text="文档A", score=0.9)]
        fake_searcher = MagicMock()
        fake_searcher.search.return_value = fake_results

        client = _make_app(reranker_client=MagicMock(), searcher=fake_searcher)
        with patch.object(settings, "auth_enabled", False):
            resp = client.post("/api/v1/retrieve", json={
                "question": "测试",
                "top_k": 5,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_retrieved"] == 1
        assert data["chunks"][0]["scores"]["rerank_score"] is None


class TestRetrieveRerankerDegraded:
    """Reranker 降级 → rerank_score 为 None，rrf_score 正常"""

    def test_reranker_failure_degrades_gracefully(self):
        fake_results = [_make_chunk("c1", score=0.9), _make_chunk("c2", score=0.7)]
        fake_searcher = MagicMock()
        fake_searcher.search.return_value = fake_results

        # Reranker 返回空列表（模拟降级）
        fake_reranker = MagicMock()
        fake_reranker.rerank.return_value = []

        client = _make_app(reranker_client=fake_reranker, searcher=fake_searcher)
        with patch.object(settings, "auth_enabled", False), \
             patch.object(settings, "rerank_fetch_multiplier", 3):
            resp = client.post("/api/v1/retrieve", json={
                "question": "测试",
                "top_k": 2,
                "use_reranker": True,
                "rerank_top_n": 2,
            })

        assert resp.status_code == 200
        data = resp.json()
        # 降级后截断到 top_k，保持原始顺序
        assert data["total_retrieved"] == 2
        # reranker 降级，无 rerank_score
        assert data["chunks"][0]["scores"]["rerank_score"] is None
        # rrf_score 仍保留原始检索分数
        assert data["chunks"][0]["scores"]["rrf_score"] is not None
