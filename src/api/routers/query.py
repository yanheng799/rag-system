"""问答路由"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.deps import get_current_user
from src.api.schemas.query import QueryRequest, QueryResponse

router = APIRouter(prefix="/api/v1", tags=["问答"], dependencies=[Depends(get_current_user)])


async def resolve_filters(
    pg_store,
    dataset_ids,
    doc_ids,
    doc_names,
) -> dict | None:
    """将 dataset_ids / doc_ids / doc_names 解析为 Milvus 过滤条件"""
    sets: list[set[str]] = []

    if dataset_ids:
        ids = await pg_store.get_doc_ids_by_dataset_ids(dataset_ids)
        sets.append(set(ids))

    if doc_ids:
        sets.append(set(doc_ids))

    if doc_names:
        ids = await pg_store.get_doc_ids_by_filenames(doc_names)
        sets.append(set(ids))

    if not sets:
        return None

    result = sets[0]
    for s in sets[1:]:
        result &= s

    if not result:
        return None
    return {"doc_id": sorted(result)}


@router.post("/query", response_model=QueryResponse, summary="问答接口")
async def query(request: Request, body: QueryRequest):
    """
    问答接口：
    1. 向量检索相关文档分块
    2. 构建 Prompt
    3. 调用 LLM 生成答案
    4. 返回答案 + 来源
    """
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    orchestrator = request.app.state.orchestrator
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="服务未就绪")

    try:
        filters = await resolve_filters(
            request.app.state.pg_store,
            body.dataset_ids,
            body.doc_ids,
            body.doc_names,
        )
        result = await orchestrator.query(
            question=body.question,
            top_k=body.top_k,
            filters=filters,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM 服务不可用: {e!s}") from None

    return QueryResponse(
        answer=result.answer,
        sources=result.sources,
        total_ms=result.total_ms,
    )
