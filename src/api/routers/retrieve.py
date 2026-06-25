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
    可选启用 Reranker 重排序。
    """
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    # Reranker 检查
    reranker_client = None
    if body.use_reranker:
        reranker_client = getattr(request.app.state, "reranker_client", None)
        if reranker_client is None:
            raise HTTPException(status_code=503, detail="Reranker 服务未配置")

    # 根据 search_mode 选择检索器
    searcher = getattr(request.app.state, f"{body.search_mode}_searcher", None)
    if searcher is None:
        raise HTTPException(status_code=503, detail=f"{body.search_mode} 检索服务未就绪")

    start_time = time.time()
    org_id = user.get("org_id", "") or ""

    # 开启 reranker 时，扩大检索召回量
    fetch_top_k = body.top_k
    if reranker_client:
        from src.config.settings import settings

        fetch_top_k = body.top_k * settings.rerank_fetch_multiplier

    logger.info(
        "检索请求: question='%s', mode=%s, top_k=%d, fetch_top_k=%d, reranker=%s, org_id=%s",
        body.question[:80],
        body.search_mode,
        body.top_k,
        fetch_top_k,
        body.use_reranker,
        org_id,
    )

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
        from src.api.routers._shared import resolve_filters

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
            results = searcher.search(question=q, top_k=fetch_top_k, filters=filters)
            logger.info("子查询 '%s' → %d 条结果", q[:30], len(results))
            for chunk in results:
                cid = chunk.metadata.chunk_id
                if cid in accumulated:
                    existing_chunk, existing_score = accumulated[cid]
                    accumulated[cid] = (existing_chunk, existing_score + chunk.score)
                else:
                    accumulated[cid] = (chunk, chunk.score)
        sorted_results = sorted(accumulated.values(), key=lambda x: x[1], reverse=True)
        chunks = [chunk for chunk, _ in sorted_results[:fetch_top_k]]
        for chunk, score in sorted_results[:fetch_top_k]:
            chunk.score = score
    else:
        chunks = searcher.search(
            question=body.question,
            top_k=fetch_top_k,
            filters=filters,
        )
    logger.info(
        "检索完成: %d 条结果, top_scores=%s",
        len(chunks),
        [round(c.score, 4) for c in chunks[:5]],
    )

    # Reranker 重排序
    if reranker_client and chunks:
        # 保存原始检索分数，用于响应中 rrf_score 展示
        original_scores = {id(c): c.score for c in chunks}
        documents = [c.full_text for c in chunks]
        rerank_results = reranker_client.rerank(
            query=body.question,
            documents=documents,
            top_n=body.rerank_top_n,
        )
        if rerank_results:
            reranked_chunks = []
            for rr in rerank_results:
                chunk = chunks[rr.index]
                chunk.rerank_score = rr.relevance_score
                chunk.score = rr.relevance_score
                reranked_chunks.append(chunk)
            chunks = reranked_chunks
            logger.info("Rerank 精排完成: %d → %d 条", len(documents), len(chunks))
        else:
            # 降级：reranker 返回空，截断到 top_k
            logger.warning("Reranker 降级，使用原始检索排序")
            chunks = chunks[: body.top_k]
    else:
        chunks = chunks[: body.top_k]

    # 构建 rrf_score 映射（hybrid + reranker 场景下保留原始 RRF 分数）
    rrf_score_map = {id(c): original_scores.get(id(c), 0.0) for c in chunks} if reranker_client else {}

    retrieval_ms = int((time.time() - start_time) * 1000)
    logger.info("请求完成: %d 条结果, 耗时=%dms", len(chunks), retrieval_ms)

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
            rrf_score=rrf_score_map.get(id(chunk)) if rrf_score_map else (chunk.score if body.search_mode == "hybrid" else None),
            rerank_score=chunk.rerank_score if body.use_reranker and chunk.rerank_score else None,
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
