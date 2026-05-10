"""向量检索模块（Phase 1）"""

from __future__ import annotations

import logging
from typing import Optional

from ingestion.embedder import Embedder
from models.chunks import (
    ChunkMetadata,
    ContentElement,
    RetrievedChunk,
)
from storage.ports import VectorStorePort

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
        filters: Optional[dict] = None,
    ) -> list[RetrievedChunk]:
        """
        向量检索流程：
        1. 对 question 向量化
        2. 调用 Milvus 检索
        3. 转换为 RetrievedChunk 列表
        """
        # 向量化查询
        embedding = self._embedder.embed_single(question)

        # Milvus 检索
        results = self._vector_store.search(
            embedding=embedding,
            top_k=top_k,
            filters=filters,
        )
        logger.info("向量检索完成: %d 条结果", len(results))

        # 转换为 RetrievedChunk
        chunks = []
        for hit in results:
            metadata = ChunkMetadata(
                chunk_id=hit["chunk_id"],
                chunk_type=hit["chunk_type"],
                source=hit["source"],
                page=hit["page"],
                chunk_index=hit["chunk_index"],
                char_count=hit["char_count"],
                created_at=hit["created_at"],
                doc_id=hit["doc_id"],
                pages=hit.get("pages", [hit["page"]]),
            )
            elements = [
                ContentElement.from_dict(e) for e in hit.get("elements", [])
            ]
            image_urls = hit.get("image_urls", [])

            chunks.append(
                RetrievedChunk(
                    metadata=metadata,
                    elements=elements,
                    full_text=hit["full_text"],
                    image_urls=image_urls,
                    score=hit["score"],
                )
            )

        return chunks
