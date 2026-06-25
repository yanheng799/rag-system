"""问答路由（SSE 流式响应）"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.api.deps import get_current_user
from src.api.routers._shared import resolve_filters
from src.api.schemas.query import QueryRequest

router = APIRouter(prefix="/api/v1", tags=["问答"])

logger = logging.getLogger(__name__)


@router.post("/query", summary="问答接口（SSE 流式）")
async def query(request: Request, body: QueryRequest, user: dict = Depends(get_current_user)):
    """
    问答接口（SSE 流式响应）：
    1. 查询改写
    2. 向量检索相关文档分块
    3. 流式调用 LLM 生成答案
    4. 返回来源信息

    SSE 事件类型：
    - status: {"phase": "rewriting" | "retrieving"}
    - token: {"content": "..."}
    - result: {"sources": [...], "total_ms": int, "rewritten_queries": [...]}
    """
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    orchestrator = request.app.state.orchestrator
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="服务未就绪")

    org_id = user.get("org_id", "") or ""

    # Reranker 检查（与 retrieve 接口一致：请求开启但未配置 → 503）
    if body.use_reranker and getattr(request.app.state, "reranker_client", None) is None:
        raise HTTPException(status_code=503, detail="Reranker 服务未配置")

    filters = await resolve_filters(
        request.app.state.pg_store,
        body.dataset_ids,
        body.doc_ids,
        body.doc_names,
        org_id=org_id,
    )

    event_stream = orchestrator.query_stream(
        question=body.question,
        top_k=body.top_k,
        user_id=user.get("user_id"),
        filters=filters,
        org_id=org_id,
        show_rewritten=body.show_rewritten,
        use_reranker=body.use_reranker,
        rerank_top_n=body.rerank_top_n,
    )

    return StreamingResponse(
        event_stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
