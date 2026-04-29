"""问答路由"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.schemas.query import QueryRequest, QueryResponse

router = APIRouter(prefix="/api/v1", tags=["问答"])


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
        result = await orchestrator.query(
            question=body.question,
            top_k=body.top_k,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM 服务不可用: {str(e)}")

    return QueryResponse(
        answer=result.answer,
        sources=result.sources,
        total_ms=result.total_ms,
    )
