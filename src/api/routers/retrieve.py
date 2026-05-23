"""检索接口"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.deps import get_current_user
from src.api.schemas.retrieve import (
    ChunkMetadataResult,
    ChunkScores,
    RetrievedChunkResult,
    RetrieveRequest,
    RetrieveResponse,
)

router = APIRouter(prefix="/api/v1", tags=["检索"])

logger = logging.getLogger(__name__)


@router.post("/retrieve", response_model=RetrieveResponse, summary="检索接口")
async def debug_retrieve(request: Request, body: RetrieveRequest, user: dict = Depends(get_current_user)):
    """
    检索接口：绕过 LLM，直接返回检索分块结果。
    支持 vector / bm25 / hybrid 三种检索模式。
    """
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    # 根据 search_mode 选择检索器
    searcher = getattr(request.app.state, f"{body.search_mode}_searcher", None)
    if searcher is None:
        raise HTTPException(status_code=503, detail=f"{body.search_mode} 检索服务未就绪")

    start_time = time.time()
    org_id = user.get("org_id", "") or ""
    logger.info("检索请求: question='%s', mode=%s, top_k=%d, org_id=%s", body.question[:80], body.search_mode, body.top_k, org_id)

    # 查询改写
    query_rewriter = getattr(request.app.state, "query_rewriter", None)
    rewritten_queries = None
    if query_rewriter:
        queries = query_rewriter.rewrite(body.question)
        if len(queries) > 1:
            rewritten_queries = queries
        logger.info("查询改写启用: %d 个查询 → %s", len(queries), queries)
    else:
        queries = [body.question]
        logger.info("查询改写跳过: rewriter 未加载（query_rewrite_enabled=false）")

    # 解析过滤参数
    filters = None
    if body.dataset_ids or body.doc_ids or body.doc_names:
        from src.api.routers.query import resolve_filters

        filters = await resolve_filters(
            request.app.state.pg_store,
            body.dataset_ids,
            body.doc_ids,
            body.doc_names,
            org_id=org_id,
        )
    logger.info("检索过滤: filters=%s", filters)

    # 多路检索 + 累加分数合并
    if len(queries) > 1:
        from src.models.chunks import RetrievedChunk

        accumulated: dict[str, tuple[RetrievedChunk, float]] = {}
        for q in queries:
            results = searcher.search(question=q, top_k=body.top_k, filters=filters)
            logger.info("子查询 '%s' → %d 条结果", q[:30], len(results))
            for chunk in results:
                cid = chunk.metadata.chunk_id
                if cid in accumulated:
                    existing_chunk, existing_score = accumulated[cid]
                    accumulated[cid] = (existing_chunk, existing_score + chunk.score)
                else:
                    accumulated[cid] = (chunk, chunk.score)
        sorted_results = sorted(accumulated.values(), key=lambda x: x[1], reverse=True)
        chunks = [chunk for chunk, _ in sorted_results[:body.top_k]]
        for chunk, score in sorted_results[:body.top_k]:
            chunk.score = score
    else:
        chunks = searcher.search(
            question=body.question,
            top_k=body.top_k,
            filters=filters,
        )
    retrieval_ms = int((time.time() - start_time) * 1000)
    logger.info(
        "检索完成: %d 条结果, 耗时=%dms, top_scores=%s",
        len(chunks),
        retrieval_ms,
        [round(c.score, 4) for c in chunks[:5]],
    )

    pg_store = request.app.state.pg_store

    # 批量查询文档的真实 filename
    unique_doc_ids = list({c.metadata.doc_id for c in chunks})
    doc_filename_map: dict[str, str] = {}
    for did in unique_doc_ids:
        doc = await pg_store.get_document(did)
        if doc:
            doc_filename_map[did] = doc.filename

    # 构建响应
    debug_chunks = []
    for idx, chunk in enumerate(chunks, 1):
        meta_dict = chunk.metadata.to_dict()
        meta_dict.pop("source", None)
        meta_dict["filename"] = doc_filename_map.get(chunk.metadata.doc_id, chunk.metadata.source)
        metadata = ChunkMetadataResult(**meta_dict)

        image_urls = [f"/api/v1/images/{url}" for url in chunk.image_urls]

        scores = ChunkScores(
            vector_score=chunk.vector_score,
            bm25_score=chunk.bm25_score,
            rrf_score=chunk.score if body.search_mode == "hybrid" else None,
        )

        debug_chunks.append(
            RetrievedChunkResult(
                rank=idx,
                metadata=metadata,
                full_text=chunk.full_text,
                scores=scores,
                image_urls=image_urls,
            )
        )

    return RetrieveResponse(
        question=body.question,
        search_mode=body.search_mode,
        total_retrieved=len(debug_chunks),
        retrieval_ms=retrieval_ms,
        chunks=debug_chunks,
        rewritten_queries=rewritten_queries,
    )
