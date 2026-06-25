"""检索接口"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.deps import get_current_user
from src.api.routers._shared import resolve_filters
from src.api.schemas.retrieve import (
    ChunkMetadataResult,
    ChunkScores,
    RetrievedChunkResult,
    RetrieveRequest,
    RetrieveResponse,
)
from src.retrieval.retrieval_service import build_doc_filename_map

router = APIRouter(prefix="/api/v1", tags=["检索"])

logger = logging.getLogger(__name__)


@router.post("/retrieve", response_model=RetrieveResponse, summary="检索接口")
async def debug_retrieve(request: Request, body: RetrieveRequest, user: dict = Depends(get_current_user)):
    """
    检索接口：绕过 LLM，直接返回检索分块结果。
    支持 vector / bm25 / hybrid 三种检索模式。
    可选启用 Reranker 重排序。

    检索流程（改写 + 多路合并 + 可选重排）统一委托 RetrievalService，与 /query 共用语义。
    """
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    # Reranker 检查（请求开启但未配置 → 503）
    if body.use_reranker and getattr(request.app.state, "reranker_client", None) is None:
        raise HTTPException(status_code=503, detail="Reranker 服务未配置")

    # 根据 search_mode 选择检索器
    searcher = getattr(request.app.state, f"{body.search_mode}_searcher", None)
    if searcher is None:
        raise HTTPException(status_code=503, detail=f"{body.search_mode} 检索服务未就绪")

    retrieval_service = request.app.state.retrieval_service

    start_time = time.time()
    org_id = user.get("org_id", "") or ""

    logger.info(
        "检索请求: question='%s', mode=%s, top_k=%d, reranker=%s, rerank_top_n=%d, org_id=%s",
        body.question[:80],
        body.search_mode,
        body.top_k,
        body.use_reranker,
        body.rerank_top_n,
        org_id,
    )

    # 查询改写（独立一步，便于回传 rewritten_queries）
    queries = retrieval_service.rewrite(body.question)
    rewritten_queries = queries if len(queries) > 1 else None

    # 解析过滤参数
    filters = None
    if body.dataset_ids or body.doc_ids or body.doc_names:
        filters = await resolve_filters(
            request.app.state.pg_store,
            body.dataset_ids,
            body.doc_ids,
            body.doc_names,
            org_id=org_id,
        )
    logger.info("检索过滤: filters=%s", filters)

    # 统一检索（多路合并 + 可选重排）；org_id 全程透传，
    # 修复此前裸检索漏传 org_id 导致不按组织隔离的漂移。
    chunks = retrieval_service.retrieve(
        searcher,
        queries,
        top_k=body.top_k,
        filters=filters,
        org_id=org_id,
        use_reranker=body.use_reranker,
        rerank_top_n=body.rerank_top_n,
    )
    logger.info(
        "检索完成: %d 条结果, top_scores=%s",
        len(chunks),
        [round(c.score, 4) for c in chunks[:5]],
    )

    retrieval_ms = int((time.time() - start_time) * 1000)
    logger.info("请求完成: %d 条结果, 耗时=%dms", len(chunks), retrieval_ms)

    pg_store = request.app.state.pg_store

    # 批量查询文档的真实 filename
    doc_filename_map = await build_doc_filename_map(pg_store, chunks)

    # 构建响应。retrieve() 不以重排分覆盖 score，故 chunk.score 始终是原始检索/合并分；
    # rrf_score 在 hybrid 或开启 reranker 时展示该原始分，rerank_score 仅在重排有效时展示。
    show_rrf = body.search_mode == "hybrid" or body.use_reranker
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
            rrf_score=chunk.score if show_rrf else None,
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
