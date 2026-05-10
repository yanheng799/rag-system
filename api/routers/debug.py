"""调试检索路由"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from api.schemas.debug import (
    DebugChunk,
    DebugChunkMetadata,
    DebugChunkScores,
    RetrieveRequest,
    RetrieveResponse,
)

router = APIRouter(prefix="/api/v1/debug", tags=["调试"])


@router.post("/retrieve", response_model=RetrieveResponse, summary="调试检索接口")
async def debug_retrieve(request: Request, body: RetrieveRequest):
    """
    调试检索接口：绕过 LLM，直接返回检索分块结果。
    用于开发和调试阶段验证检索质量。
    """
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    vector_searcher = request.app.state.vector_searcher
    if vector_searcher is None:
        raise HTTPException(status_code=503, detail="检索服务未就绪")

    start_time = time.time()
    chunks = vector_searcher.search(
        question=body.question,
        top_k=body.top_k,
    )
    retrieval_ms = int((time.time() - start_time) * 1000)

    # 构建 prompt（可选）
    prompt_text = None
    if body.show_prompt:
        from orchestration.prompt_builder import PromptBuilder

        prompt_builder = PromptBuilder()
        messages = prompt_builder.build(body.question, chunks)
        prompt_text = messages[1]["content"] if len(messages) > 1 else ""

    signed_url_service = request.app.state.signed_url_service

    # 构建响应
    debug_chunks = []
    for idx, chunk in enumerate(chunks, 1):
        meta_dict = chunk.metadata.to_dict()
        meta_dict["filename"] = meta_dict.pop("source")
        metadata = DebugChunkMetadata(**meta_dict)

        image_urls = []
        for url in chunk.image_urls:
            if signed_url_service:
                image_urls.append(signed_url_service.sign(url))
            else:
                image_urls.append(url)

        debug_chunks.append(
            DebugChunk(
                rank=idx,
                metadata=metadata,
                full_text=chunk.full_text,
                scores=DebugChunkScores(vector_score=chunk.score),
                image_urls=image_urls,
            )
        )

    return RetrieveResponse(
        question=body.question,
        search_mode=body.search_mode,
        total_retrieved=len(debug_chunks),
        retrieval_ms=retrieval_ms,
        chunks=debug_chunks,
        prompt=prompt_text,
    )
