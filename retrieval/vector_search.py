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
        4. 按 group_id 合并被拆分的分块
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
                group_id=hit.get("group_id", ""),
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

        # 按 group_id 合并被拆分的分块
        chunks = self._merge_grouped_chunks(chunks)

        return chunks

    def _merge_grouped_chunks(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """合并同一 group_id 的分块，返回完整段落"""
        # 收集需要合并的 group
        group_map: dict[str, list[RetrievedChunk]] = {}
        for chunk in chunks:
            gid = chunk.metadata.group_id
            if gid:
                group_map.setdefault(gid, []).append(chunk)

        if not group_map:
            return chunks

        # 批量获取兄弟分块
        try:
            siblings_data = self._vector_store.fetch_by_group_ids(list(group_map.keys()))
        except Exception:
            logger.warning("获取兄弟分块失败，跳过合并")
            return chunks

        # 将兄弟分块转为 RetrievedChunk 并补充到 group_map
        for hit in siblings_data:
            gid = hit.get("group_id", "")
            if gid not in group_map:
                continue
            existing_ids = {c.metadata.chunk_id for c in group_map[gid]}
            if hit["chunk_id"] in existing_ids:
                continue
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
                group_id=gid,
            )
            elements = [
                ContentElement.from_dict(e) for e in hit.get("elements", [])
            ]
            group_map[gid].append(
                RetrievedChunk(
                    metadata=metadata,
                    elements=elements,
                    full_text=hit["full_text"],
                    image_urls=hit.get("image_urls", []),
                    score=0.0,
                )
            )

        # 合并同组：拼接 full_text，取最高分
        merged: list[RetrievedChunk] = []
        seen_groups: set[str] = set()
        for chunk in chunks:
            gid = chunk.metadata.group_id
            if not gid:
                merged.append(chunk)
                continue
            if gid in seen_groups:
                continue
            seen_groups.add(gid)

            group = sorted(
                group_map[gid],
                key=lambda c: (c.metadata.page, c.metadata.chunk_index),
            )
            chunk.full_text = "\n".join(c.full_text for c in group)
            chunk.score = max(c.score for c in group)
            # 合并 image_urls
            all_urls = []
            for c in group:
                all_urls.extend(c.image_urls)
            chunk.image_urls = all_urls
            merged.append(chunk)

        logger.info("分块合并: %d → %d 条结果", len(chunks), len(merged))
        return merged
