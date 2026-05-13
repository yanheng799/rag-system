"""分块合并工具：按 group_id 合并被拆分的分块"""

from __future__ import annotations

import logging
from collections.abc import Callable

from src.models.chunks import ChunkMetadata, ContentElement, RetrievedChunk

logger = logging.getLogger(__name__)


def merge_grouped_chunks(
    chunks: list[RetrievedChunk],
    fetch_fn: Callable[[list[str]], list[dict]],
) -> list[RetrievedChunk]:
    """
    合并同一 group_id 的分块，返回完整段落。

    Args:
        chunks: 检索返回的初始分块列表
        fetch_fn: 按 group_id 列表获取兄弟分块的函数
    """
    group_map: dict[str, list[RetrievedChunk]] = {}
    for chunk in chunks:
        gid = chunk.metadata.group_id
        if gid:
            group_map.setdefault(gid, []).append(chunk)

    if not group_map:
        return chunks

    try:
        siblings_data = fetch_fn(list(group_map.keys()))
    except Exception:
        logger.warning("获取兄弟分块失败，跳过合并")
        return chunks

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
        elements = [ContentElement.from_dict(e) for e in hit.get("elements", [])]
        group_map[gid].append(
            RetrievedChunk(
                metadata=metadata,
                elements=elements,
                full_text=hit["full_text"],
                image_urls=hit.get("image_urls", []),
                score=0.0,
            )
        )

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
        all_urls = []
        all_elements = []
        all_pages = []
        for c in group:
            all_urls.extend(c.image_urls)
            all_elements.extend(c.elements)
            all_pages.extend(c.metadata.pages)
        chunk.image_urls = all_urls
        chunk.elements = all_elements
        chunk.metadata.pages = sorted(set(all_pages))
        merged.append(chunk)

    logger.info("分块合并: %d → %d 条结果", len(chunks), len(merged))
    return merged


def hit_to_chunk(hit: dict) -> RetrievedChunk:
    """将 Milvus 命中记录转为 RetrievedChunk"""
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
    elements = [ContentElement.from_dict(e) for e in hit.get("elements", [])]
    return RetrievedChunk(
        metadata=metadata,
        elements=elements,
        full_text=hit["full_text"],
        image_urls=hit.get("image_urls", []),
        score=hit["score"],
    )
