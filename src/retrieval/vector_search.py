"""向量检索模块"""

from __future__ import annotations

import logging

from src.ingestion.embedder import Embedder
from src.models.chunks import RetrievedChunk
from src.retrieval.chunk_merge import hit_to_chunk, merge_grouped_chunks
from src.storage.ports import VectorStorePort

logger = logging.getLogger(__name__)


class VectorSearcher:
    """基于 Milvus 的向量检索"""

    def __init__(
        self,
        vector_store: VectorStorePort,
        embedder: Embedder,
    ):
        self._vector_store = vector_store
        self._embedder = embedder

    def search(
        self,
        question: str,
        top_k: int = 50,
        filters: dict | None = None,
        org_id: str | None = None,
    ) -> list[RetrievedChunk]:
        """
        向量检索流程：
        1. 对 question 向量化
        2. 调用 Milvus 检索
        3. 转换为 RetrievedChunk 列表
        4. 按 group_id 合并被拆分的分块
        """
        embedding = self._embedder.embed_single(question)

        results = self._vector_store.search(
            embedding=embedding,
            top_k=top_k,
            filters=filters,
            org_id=org_id,
        )
        logger.info("向量检索完成: %d 条结果", len(results))

        chunks = [hit_to_chunk(hit) for hit in results]
        chunks = merge_grouped_chunks(chunks, self._vector_store.fetch_by_group_ids)
        return chunks
