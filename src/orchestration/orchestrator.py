"""RAG 编排主流程"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from src.models.chunks import RetrievedChunk
from src.models.documents import QueryLogRecord
from src.orchestration.llm_client import LLMClient
from src.orchestration.prompt_builder import PromptBuilder
from src.retrieval.hybrid_search import HybridSearcher
from src.retrieval.retrieval_service import RetrievalService, build_doc_filename_map
from src.retrieval.vector_search import VectorSearcher
from src.storage.ports import DocumentStorePort

logger = logging.getLogger(__name__)


def _sse_event(event: str, data: dict) -> str:
    """格式化 SSE 事件"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@dataclass
class QueryResponse:
    """查询响应（非流式场景保留）"""

    answer: str
    sources: list[dict]
    total_ms: int
    rewritten_queries: list[str] | None = None


class RAGOrchestrator:
    """RAG 编排器：串联检索 → Prompt 构建 → LLM 调用 → 后处理

    检索逻辑（改写 + 多路检索合并 + 可选 Reranker）委托给 RetrievalService，
    与 /api/v1/retrieve 共用同一套检索语义；本类只负责 SSE 流式编排、Prompt
    构建、LLM 调用、来源构建与查询日志。
    """

    def __init__(
        self,
        searcher: VectorSearcher | HybridSearcher,
        retrieval_service: RetrievalService,
        llm_client: LLMClient,
        prompt_builder: PromptBuilder,
        doc_store: DocumentStorePort,
    ):
        self._searcher = searcher
        self._retrieval_service = retrieval_service
        self._llm = llm_client
        self._prompt_builder = prompt_builder
        self._doc_store = doc_store

    async def query_stream(
        self,
        question: str,
        top_k: int = 5,
        user_id: str | None = None,
        filters: dict | None = None,
        org_id: str | None = None,
        show_rewritten: bool = False,
        use_reranker: bool = False,
        rerank_top_n: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        SSE 流式问答：
        1. yield status: rewriting
        2. yield status: retrieving
        3. yield token (逐个)
        4. yield result (sources + total_ms + rewritten_queries)
        5. 写入查询日志
        """
        start_time = time.time()
        logger.info(
            "查询开始: question='%s', top_k=%d, filters=%s, org_id=%s, use_reranker=%s",
            question[:80],
            top_k,
            filters,
            org_id,
            use_reranker,
        )

        # 1. 查询改写（独立一步，保留 rewriting/retrieving 两阶段 SSE 提示）
        yield _sse_event("status", {"phase": "rewriting"})
        queries = self._retrieval_service.rewrite(question)

        # 2. 多路检索 + 合并去重（+ 可选 Reranker 重排）
        yield _sse_event("status", {"phase": "retrieving"})
        retrieval_start = time.time()
        chunks = self._retrieval_service.retrieve(
            self._searcher,
            queries,
            top_k=top_k,
            filters=filters,
            org_id=org_id,
            use_reranker=use_reranker,
            rerank_top_n=rerank_top_n,
        )
        retrieval_ms = int((time.time() - retrieval_start) * 1000)

        # 2.5 批量查询文档的真实 filename
        doc_filename_map = await build_doc_filename_map(self._doc_store, chunks)

        # 3. 构建 Prompt
        messages = self._prompt_builder.build(question, chunks, doc_filename_map)

        # 4. 流式调用 LLM，逐 token 推送
        llm_start = time.time()
        answer_parts: list[str] = []
        for token in self._llm.complete(messages, stream=True):
            answer_parts.append(token)
            yield _sse_event("token", {"content": token})
        answer = "".join(answer_parts)
        llm_ms = int((time.time() - llm_start) * 1000)

        # 5. 推送结果元数据
        sources = self._build_response_sources(chunks, doc_filename_map)
        total_ms = int((time.time() - start_time) * 1000)

        yield _sse_event("result", {
            "sources": sources,
            "total_ms": total_ms,
            "rewritten_queries": queries if show_rewritten and len(queries) > 1 else None,
        })

        # 6. 写入查询日志
        log = QueryLogRecord(
            log_id=f"qlog_{uuid.uuid4().hex[:12]}",
            question=question,
            answer=answer,
            retrieved_chunks=[{"chunk_id": c.metadata.chunk_id, "score": c.score} for c in chunks],
            retrieval_ms=retrieval_ms,
            llm_ms=llm_ms,
            total_ms=total_ms,
            org_id=org_id,
            created_by=user_id,
        )
        await self._doc_store.save_query_log(log)

        logger.info(
            "查询完成: queries=%d, retrieval=%dms, llm=%dms, total=%dms, chunks=%d",
            len(queries),
            retrieval_ms,
            llm_ms,
            total_ms,
            len(chunks),
        )

    def _build_response_sources(self, chunks: list[RetrievedChunk], doc_filename_map: dict[str, str]) -> list[dict]:
        """构建响应中的 sources 列表，替换为代理 URL + 真实 filename"""
        sources = []
        for chunk in chunks:
            elements = []
            for elem in chunk.elements:
                elem_dict = elem.to_dict()
                if elem_dict.get("image_url"):
                    elem_dict["image_url"] = f"/api/v1/images/{elem_dict['image_url']}"
                elements.append(elem_dict)

            metadata = chunk.metadata.to_dict()
            metadata["score"] = chunk.score
            metadata.pop("source", None)
            metadata["filename"] = doc_filename_map.get(chunk.metadata.doc_id, chunk.metadata.source)

            sources.append(
                {
                    "metadata": metadata,
                    "elements": elements,
                }
            )
        return sources
