"""统一检索服务：查询改写 + 多路检索合并 + 可选 Reranker 重排。

供 /api/v1/query（经 RAGOrchestrator）与 /api/v1/retrieve 两个接口共用，
消除此前散落在 orchestrator._multi_query_search 与 retrieve.py 内联逻辑中的重复，
并统一 org_id 透传与 Reranker 召回/截断语义。

设计要点：
- searcher 按调用传入（非构造绑定），以同时满足 retrieve 的 per-request 模式切换
  （vector/bm25/hybrid）与 orchestrator 的固定 searcher。
- retrieve() 返回裸 RetrievedChunk，保持同步、不依赖文档存储；filename 富化由调用方
  在检索完成后通过 _shared.build_doc_filename_map 完成。
- chunk.score 始终保留检索/合并分；重排分写入 chunk.rerank_score，二者互不覆盖，
  使调用方能同时展示原始检索分与重排分。
"""

from __future__ import annotations

import logging

from src.config.settings import settings
from src.models.chunks import RetrievedChunk
from src.orchestration.query_rewriter import QueryRewriter
from src.retrieval.reranker import RerankerClient

logger = logging.getLogger(__name__)


async def build_doc_filename_map(
    doc_store,
    chunks: list[RetrievedChunk],
) -> dict[str, str]:
    """批量查询 chunks 涉及文档的真实 filename，返回 doc_id -> filename 映射。

    供编排层（orchestrator 构建 Prompt/sources）与 API 层（retrieve 展示）共用，
    放在检索层以避免编排层反向依赖 API 层。
    """
    unique_doc_ids = list({c.metadata.doc_id for c in chunks})
    mapping: dict[str, str] = {}
    for did in unique_doc_ids:
        doc = await doc_store.get_document(did)
        if doc:
            mapping[did] = doc.filename
    return mapping


class RetrievalService:
    """检索编排核心：rewrite + retrieve，searcher 按调用传入以支持多模式切换。"""

    def __init__(
        self,
        query_rewriter: QueryRewriter | None = None,
        reranker: RerankerClient | None = None,
    ):
        self._query_rewriter = query_rewriter
        self._reranker = reranker

    def rewrite(self, question: str) -> list[str]:
        """查询改写：返回 [原始问题, 子查询...]；未配置改写器时仅返回原始问题。"""
        if self._query_rewriter:
            queries = self._query_rewriter.rewrite(question)
            if len(queries) > 1:
                logger.info("查询改写启用: %d 个查询 → %s", len(queries), queries)
                return queries
        logger.info("查询改写跳过: rewriter 未加载")
        return [question]

    def retrieve(
        self,
        searcher,
        queries: list[str],
        top_k: int,
        filters: dict | None = None,
        org_id: str | None = None,
        use_reranker: bool = False,
        rerank_top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        """
        多路检索 + 合并去重 + 可选重排，返回裸 RetrievedChunk 列表。

        - use_reranker=False：每路召回 top_k，合并后截断到 top_k。
        - use_reranker=True：每路召回 top_k × rerank_fetch_multiplier，合并后交给
          Reranker 重排，截断到 rerank_top_n；Reranker 降级（返回空）时回退截断到 top_k。
        - chunk.score 始终保留检索/合并分；重排分写入 chunk.rerank_score，互不覆盖。
        - org_id 全程透传给 searcher.search，保证按组织隔离检索。
        """
        recall_k = top_k * settings.rerank_fetch_multiplier if use_reranker else top_k

        # 多路检索 + 按 chunk_id 累加分数去重
        accumulated: dict[str, tuple[RetrievedChunk, float]] = {}
        for q in queries:
            results = searcher.search(q, top_k=recall_k, filters=filters, org_id=org_id)
            for chunk in results:
                cid = chunk.metadata.chunk_id
                if cid in accumulated:
                    existing_chunk, existing_score = accumulated[cid]
                    accumulated[cid] = (existing_chunk, existing_score + chunk.score)
                else:
                    accumulated[cid] = (chunk, chunk.score)

        # 按累加分数降序，截断到 recall_k，并把累加分写回 chunk.score
        ranked = sorted(accumulated.values(), key=lambda x: x[1], reverse=True)[:recall_k]
        chunks: list[RetrievedChunk] = []
        for chunk, score in ranked:
            chunk.score = score
            chunks.append(chunk)
        logger.info("多路检索合并: %d 路查询 → %d 个去重结果", len(queries), len(chunks))

        # 可选 Reranker 重排
        if use_reranker and self._reranker and chunks:
            return self._rerank(queries[0], chunks, top_k, rerank_top_n)

        return chunks[:top_k]

    def _rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int,
        rerank_top_n: int | None,
    ) -> list[RetrievedChunk]:
        """Reranker 重排：成功则返回 rerank_top_n 条（写入 rerank_score）；降级则回退 top_k。"""
        effective_top_n = rerank_top_n or settings.rerank_top_k
        documents = [c.full_text for c in chunks]
        rerank_results = self._reranker.rerank(
            query=query,
            documents=documents,
            top_n=effective_top_n,
        )
        if not rerank_results:
            logger.warning("Reranker 降级，回退原始检索排序（截断到 top_k=%d）", top_k)
            return chunks[:top_k]

        reranked: list[RetrievedChunk] = []
        for rr in rerank_results:
            chunk = chunks[rr.index]
            chunk.rerank_score = rr.relevance_score
            reranked.append(chunk)
        logger.info("Rerank 精排完成: %d → %d 条", len(documents), len(reranked))
        return reranked
