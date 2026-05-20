"""混合检索：向量 + BM25，RRF 融合"""

from __future__ import annotations

import logging

from src.models.chunks import RetrievedChunk
from src.retrieval.bm25_search import BM25Searcher
from src.retrieval.rrf_fusion import rrf_fuse
from src.retrieval.vector_search import VectorSearcher

logger = logging.getLogger(__name__)


class HybridSearcher:
    """混合检索器：向量检索 + BM25 全文检索 + RRF 融合"""

    def __init__(
        self,
        vector_searcher: VectorSearcher,
        bm25_searcher: BM25Searcher,
    ):
        self._vector_searcher = vector_searcher
        self._bm25_searcher = bm25_searcher

    def search(
        self,
        question: str,
        top_k: int = 50,
        filters: dict | None = None,
        org_id: str | None = None,
    ) -> list[RetrievedChunk]:
        """
        混合检索流程：
        1. 执行向量检索和 BM25 检索
        2. 使用 RRF 融合两路结果
        3. 返回融合后排序结果
        """
        vector_chunks = self._vector_searcher.search(question, top_k=top_k, filters=filters, org_id=org_id)
        bm25_chunks = self._bm25_searcher.search(question, top_k=top_k, filters=filters, org_id=org_id)

        logger.info(
            "混合检索: 向量 %d 条, BM25 %d 条",
            len(vector_chunks),
            len(bm25_chunks),
        )

        fused = rrf_fuse(vector_chunks, bm25_chunks)
        logger.info("RRF 融合后: %d 条结果", len(fused))
        return fused
