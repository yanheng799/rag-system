"""RAG 编排主流程"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass

from src.models.chunks import RetrievedChunk
from src.models.documents import QueryLogRecord
from src.orchestration.llm_client import LLMClient
from src.orchestration.prompt_builder import PromptBuilder
from src.retrieval.hybrid_search import HybridSearcher
from src.retrieval.vector_search import VectorSearcher
from src.storage.ports import DocumentStorePort
from src.storage.signed_url_service import SignedUrlService

logger = logging.getLogger(__name__)


@dataclass
class QueryResponse:
    """查询响应"""

    answer: str
    sources: list[dict]
    total_ms: int


class RAGOrchestrator:
    """RAG 编排器：串联检索 → Prompt 构建 → LLM 调用 → 后处理"""

    def __init__(
        self,
        searcher: VectorSearcher | HybridSearcher,
        llm_client: LLMClient,
        prompt_builder: PromptBuilder,
        doc_store: DocumentStorePort,
        signed_url_service: SignedUrlService,
    ):
        self._searcher = searcher
        self._llm = llm_client
        self._prompt_builder = prompt_builder
        self._doc_store = doc_store
        self._signed_url = signed_url_service

    async def query(
        self,
        question: str,
        top_k: int = 5,
        user_id: str | None = None,
        filters: dict | None = None,
    ) -> QueryResponse:
        """
        完整问答流程：
        1. 向量检索
        2. 构建 Prompt
        3. 调用 LLM
        4. 后处理（签名 URL 替换）
        5. 写入查询日志
        """
        start_time = time.time()

        # 1. 向量检索
        retrieval_start = time.time()
        chunks = self._searcher.search(question, top_k=top_k, filters=filters)
        retrieval_ms = int((time.time() - retrieval_start) * 1000)

        # 2. 构建 Prompt
        messages = self._prompt_builder.build(question, chunks)

        # 3. 调用 LLM
        llm_start = time.time()
        answer = self._llm.complete(messages)
        llm_ms = int((time.time() - llm_start) * 1000)

        # 4. 后处理：签名 URL 替换 + 真实 filename
        sources = await self._build_response_sources(chunks)

        total_ms = int((time.time() - start_time) * 1000)

        # 5. 写入查询日志
        log = QueryLogRecord(
            log_id=f"qlog_{uuid.uuid4().hex[:12]}",
            question=question,
            answer=answer,
            retrieved_chunks=[{"chunk_id": c.metadata.chunk_id, "score": c.score} for c in chunks],
            retrieval_ms=retrieval_ms,
            llm_ms=llm_ms,
            total_ms=total_ms,
            created_by=user_id,
        )
        await self._doc_store.save_query_log(log)

        logger.info(
            "查询完成: retrieval=%dms, llm=%dms, total=%dms, chunks=%d",
            retrieval_ms,
            llm_ms,
            total_ms,
            len(chunks),
        )

        return QueryResponse(
            answer=answer,
            sources=sources,
            total_ms=total_ms,
        )

    async def query_stream(
        self,
        question: str,
        top_k: int = 5,
        user_id: str | None = None,
        filters: dict | None = None,
    ):
        """
        流式问答：
        1. 先执行检索
        2. 流式调用 LLM，逐 token yield
        3. 最后 yield 来源信息
        """
        # 检索
        chunks = self._searcher.search(question, top_k=top_k, filters=filters)
        messages = self._prompt_builder.build(question, chunks)

        # 流式 LLM
        for token in self._llm.complete(messages, stream=True):
            yield {"type": "token", "content": token}

        # 来源
        sources = await self._build_response_sources(chunks)
        yield {"type": "sources", "sources": sources}
        yield {"type": "done"}

    async def _build_response_sources(self, chunks: list[RetrievedChunk]) -> list[dict]:
        """构建响应中的 sources 列表，替换签名 URL + 真实 filename"""
        # 批量查询文档的真实 filename
        unique_doc_ids = list({c.metadata.doc_id for c in chunks})
        doc_filename_map: dict[str, str] = {}
        for did in unique_doc_ids:
            doc = await self._doc_store.get_document(did)
            if doc:
                doc_filename_map[did] = doc.filename

        sources = []
        for chunk in chunks:
            # 签名 URL 替换
            elements = []
            for elem in chunk.elements:
                elem_dict = elem.to_dict()
                if elem_dict.get("image_url"):
                    elem_dict["image_url"] = self._signed_url.sign(elem_dict["image_url"])
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
