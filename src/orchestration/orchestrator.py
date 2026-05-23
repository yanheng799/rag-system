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
from src.orchestration.query_rewriter import QueryRewriter
from src.retrieval.hybrid_search import HybridSearcher
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
    """RAG 编排器：串联检索 → Prompt 构建 → LLM 调用 → 后处理"""

    def __init__(
        self,
        searcher: VectorSearcher | HybridSearcher,
        llm_client: LLMClient,
        prompt_builder: PromptBuilder,
        doc_store: DocumentStorePort,
        query_rewriter: QueryRewriter | None = None,
    ):
        self._searcher = searcher
        self._llm = llm_client
        self._prompt_builder = prompt_builder
        self._doc_store = doc_store
        self._query_rewriter = query_rewriter

    async def query_stream(
        self,
        question: str,
        top_k: int = 5,
        user_id: str | None = None,
        filters: dict | None = None,
        org_id: str | None = None,
        show_rewritten: bool = False,
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
        logger.info("查询开始: question='%s', top_k=%d, filters=%s, org_id=%s", question[:80], top_k, filters, org_id)

        # 1. 查询改写
        yield _sse_event("status", {"phase": "rewriting"})
        if self._query_rewriter:
            queries = self._query_rewriter.rewrite(question)
        else:
            queries = [question]

        # 2. 多路检索 + 合并去重
        yield _sse_event("status", {"phase": "retrieving"})
        retrieval_start = time.time()
        chunks = self._multi_query_search(queries, top_k=top_k, filters=filters, org_id=org_id)
        retrieval_ms = int((time.time() - retrieval_start) * 1000)

        # 2.5 批量查询文档的真实 filename
        unique_doc_ids = list({c.metadata.doc_id for c in chunks})
        doc_filename_map: dict[str, str] = {}
        for did in unique_doc_ids:
            doc = await self._doc_store.get_document(did)
            if doc:
                doc_filename_map[did] = doc.filename

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

    def _multi_query_search(
        self,
        queries: list[str],
        top_k: int = 5,
        filters: dict | None = None,
        org_id: str | None = None,
    ) -> list[RetrievedChunk]:
        """多路查询检索，按 chunk_id 累加分数后去重"""
        if len(queries) == 1:
            return self._searcher.search(queries[0], top_k=top_k, filters=filters, org_id=org_id)

        accumulated: dict[str, tuple[RetrievedChunk, float]] = {}

        for q in queries:
            results = self._searcher.search(q, top_k=top_k, filters=filters, org_id=org_id)
            for chunk in results:
                cid = chunk.metadata.chunk_id
                if cid in accumulated:
                    existing_chunk, existing_score = accumulated[cid]
                    accumulated[cid] = (existing_chunk, existing_score + chunk.score)
                else:
                    accumulated[cid] = (chunk, chunk.score)

        # 按累加分数降序排序
        sorted_chunks = sorted(accumulated.values(), key=lambda x: x[1], reverse=True)
        result = []
        for chunk, score in sorted_chunks[:top_k]:
            chunk.score = score
            result.append(chunk)

        logger.info("多路检索合并: %d 路查询 → %d 个去重结果", len(queries), len(result))
        return result

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
