"""BM25 全文检索（基于 Milvus 原生 BM25）"""

from __future__ import annotations

import logging

from src.models.chunks import RetrievedChunk
from src.retrieval.chunk_merge import hit_to_chunk, merge_grouped_chunks
from src.storage.milvus_store import MilvusStore

logger = logging.getLogger(__name__)


class BM25Searcher:
    """基于 Milvus 原生 BM25 的全文检索"""

    def __init__(self, milvus_store: MilvusStore):
        self._store = milvus_store

    def search(
        self,
        question: str,
        top_k: int = 50,
        filters: dict | None = None,
        org_id: str | None = None,
    ) -> list[RetrievedChunk]:
        """
        BM25 检索流程：
        1. 将查询文本直接传给 Milvus BM25 搜索
        2. 转换为 RetrievedChunk 列表
        3. 按 group_id 合并被拆分的分块
        """
        results = self._store.bm25_search(
            query_text=question,
            top_k=top_k,
            filters=filters,
            org_id=org_id,
        )
        logger.info("BM25 检索完成: %d 条结果", len(results))

        chunks = [hit_to_chunk(hit) for hit in results]
        chunks = merge_grouped_chunks(chunks, self._store.fetch_by_group_ids)
        return chunks
