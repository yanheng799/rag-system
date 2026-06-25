"""RetrievalService 单元测试：rewrite + 多路检索合并 + Reranker 重排的统一契约。

用确定性 fake（FakeSearcher/FakeReranker/FakeRewriter）在固定输入上断言：
合并去重、分数累加、Reranker 过召+截断、降级回退、org_id/filters 透传。
这些断言即统一后的契约——retrieve 召回路径相对旧 retrieve.py 的有意变化
（rerank_score 不再覆盖 score）也在此固定。
"""

import pytest

from src.config.settings import settings
from src.models.chunks import ChunkMetadata, RetrievedChunk
from src.retrieval.retrieval_service import RetrievalService
from src.retrieval.reranker import RerankResult


def _chunk(chunk_id: str, score: float = 0.5, full_text: str = "内容") -> RetrievedChunk:
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


class FakeSearcher:
    """记录调用参数，按查询返回预设结果（未命中则返回 default）。"""

    def __init__(self, results_by_query=None, default=None):
        self._by_query = results_by_query or {}
        self._default = default or []
        self.calls: list[tuple] = []  # (question, top_k, filters, org_id)

    def search(self, question, top_k=50, filters=None, org_id=None):
        self.calls.append((question, top_k, filters, org_id))
        return [c for c in self._by_query.get(question, self._default)]


class FakeReranker:
    def __init__(self, results):
        self._results = results
        self.last_call = None

    def rerank(self, query, documents, top_n=5):
        self.last_call = (query, list(documents), top_n)
        return self._results


class FakeRewriter:
    def __init__(self, queries):
        self._queries = queries

    def rewrite(self, question):
        return self._queries


class TestRewrite:
    def test_no_rewriter_returns_original_only(self):
        svc = RetrievalService()
        assert svc.rewrite("什么是 RAG") == ["什么是 RAG"]

    def test_rewriter_returns_expansion(self):
        svc = RetrievalService(
            query_rewriter=FakeRewriter(["什么是 RAG", "RAG 概念", "检索增强生成"])
        )
        assert svc.rewrite("什么是 RAG") == ["什么是 RAG", "RAG 概念", "检索增强生成"]

    def test_rewriter_no_expansion_falls_back_to_original(self):
        svc = RetrievalService(query_rewriter=FakeRewriter(["什么是 RAG"]))
        assert svc.rewrite("什么是 RAG") == ["什么是 RAG"]


class TestRetrieveNoReranker:
    def test_single_query_returns_sorted_chunks(self):
        searcher = FakeSearcher(default=[_chunk("c2", 0.7), _chunk("c1", 0.9)])
        results = RetrievalService().retrieve(searcher, ["q"], top_k=5)
        assert [r.metadata.chunk_id for r in results] == ["c1", "c2"]
        assert results[0].score == 0.9

    def test_truncates_to_top_k(self):
        chunks = [_chunk(f"c{i}", score=1.0 - i * 0.1) for i in range(6)]
        searcher = FakeSearcher(default=chunks)
        results = RetrievalService().retrieve(searcher, ["q"], top_k=2)
        assert len(results) == 2
        assert [r.metadata.chunk_id for r in results] == ["c0", "c1"]

    def test_multi_query_accumulates_duplicate_scores(self):
        # 同一 chunk_id 在两路查询中各出现一次，累加分数
        c1 = _chunk("c1", 0.5)
        searcher = FakeSearcher(
            results_by_query={"q1": [c1], "q2": [_chunk("c1", 0.3)]}
        )
        results = RetrievalService().retrieve(searcher, ["q1", "q2"], top_k=5)
        assert len(results) == 1
        assert results[0].metadata.chunk_id == "c1"
        assert results[0].score == pytest.approx(0.8)

    def test_passes_org_id_and_filters_to_searcher(self):
        searcher = FakeSearcher(default=[_chunk("c1")])
        RetrievalService().retrieve(
            searcher, ["q"], top_k=5, filters={"doc_id": "d1"}, org_id="orgA"
        )
        assert searcher.calls[0] == ("q", 5, {"doc_id": "d1"}, "orgA")

    def test_recall_equals_top_k_without_reranker(self):
        searcher = FakeSearcher(default=[_chunk("c1")])
        RetrievalService().retrieve(searcher, ["q"], top_k=7)
        assert searcher.calls[0][1] == 7


class TestRetrieveReranker:
    def test_overfetches_and_truncates_to_rerank_top_n(self, monkeypatch):
        monkeypatch.setattr(settings, "rerank_fetch_multiplier", 3)
        chunks = [
            _chunk(f"c{i}", score=0.9 - i * 0.1, full_text=f"文档{i}") for i in range(6)
        ]
        searcher = FakeSearcher(default=chunks)
        # reranker 把 c2 排第一、c0 排第二（与原始顺序不同）
        reranker = FakeReranker(
            [RerankResult(index=2, relevance_score=0.95), RerankResult(index=0, relevance_score=0.88)]
        )
        svc = RetrievalService(reranker=reranker)

        results = svc.retrieve(searcher, ["q"], top_k=2, use_reranker=True, rerank_top_n=2)

        # 召回放大：top_k=2 × multiplier=3 = 6
        assert searcher.calls[0][1] == 6
        # reranker 用原始问题（queries[0]）、top_n=rerank_top_n
        assert reranker.last_call[0] == "q"
        assert reranker.last_call[2] == 2
        # 返回 rerank 顺序，截断到 rerank_top_n=2
        assert [r.metadata.chunk_id for r in results] == ["c2", "c0"]
        # rerank_score 写入；原始检索分 score 保留不被覆盖
        assert results[0].rerank_score == 0.95
        assert results[0].score == 0.7  # c2 原始分 0.9 - 0.2
        assert results[1].rerank_score == 0.88

    def test_degradation_falls_back_to_top_k(self, monkeypatch):
        monkeypatch.setattr(settings, "rerank_fetch_multiplier", 3)
        searcher = FakeSearcher(default=[_chunk("c1", 0.9), _chunk("c2", 0.7)])
        reranker = FakeReranker([])  # 降级：返回空
        svc = RetrievalService(reranker=reranker)

        results = svc.retrieve(searcher, ["q"], top_k=2, use_reranker=True, rerank_top_n=2)

        # 回退原始排序，截断到 top_k=2
        assert [r.metadata.chunk_id for r in results] == ["c1", "c2"]
        assert results[0].rerank_score == 0.0

    def test_use_reranker_without_configured_reranker_skips_rerank(self, monkeypatch):
        # 防御：use_reranker=True 但服务未注入 reranker → 等同未开，返回 top_k
        monkeypatch.setattr(settings, "rerank_fetch_multiplier", 3)
        searcher = FakeSearcher(default=[_chunk("c1", 0.9), _chunk("c2", 0.7)])
        svc = RetrievalService(reranker=None)

        results = svc.retrieve(searcher, ["q"], top_k=2, use_reranker=True)
        assert [r.metadata.chunk_id for r in results] == ["c1", "c2"]
        assert results[0].rerank_score == 0.0
