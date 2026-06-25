"""RAGOrchestrator 单测：验证检索委托 RetrievalService、SSE 事件顺序、
use_reranker/rerank_top_n 透传、查询日志写入。

orchestrator 现为薄编排层，检索逻辑全部委托，故用 fake 替换 retrieval_service /
llm / prompt_builder / doc_store，只断言编排行为。
"""

import pytest

from src.models.chunks import ChunkMetadata, RetrievedChunk
from src.orchestration.orchestrator import RAGOrchestrator


def _chunk(cid: str) -> RetrievedChunk:
    return RetrievedChunk(
        metadata=ChunkMetadata(
            chunk_id=cid,
            chunk_type="text",
            source="s.pdf",
            page=1,
            chunk_index=0,
            char_count=1,
            created_at="2024-01-01T00:00:00",
            doc_id="doc1",
        ),
        elements=[],
        full_text="x",
        score=0.5,
    )


class FakeRetrievalService:
    def __init__(self, chunks):
        self._chunks = chunks
        self.retrieve_calls: list[dict] = []

    def rewrite(self, question):
        return [question, "子查询"]

    def retrieve(self, searcher, queries, top_k=None, filters=None, org_id=None,
                 use_reranker=False, rerank_top_n=None):
        self.retrieve_calls.append(
            {
                "searcher": searcher,
                "queries": queries,
                "top_k": top_k,
                "filters": filters,
                "org_id": org_id,
                "use_reranker": use_reranker,
                "rerank_top_n": rerank_top_n,
            }
        )
        return list(self._chunks)


class FakeLLM:
    def complete(self, messages, stream=False):
        yield from ["你好", "世界"]


class FakePromptBuilder:
    def build(self, question, chunks, doc_filename_map):
        return [{"role": "user", "content": question}]


class FakeDocStore:
    def __init__(self):
        self.saved_logs = []

    async def get_document(self, did):
        return type("Doc", (), {"filename": "file.pdf"})()

    async def save_query_log(self, log):
        self.saved_logs.append(log)


@pytest.mark.asyncio
async def test_query_stream_delegates_and_emits_sse_in_order():
    retrieval = FakeRetrievalService([_chunk("c1")])
    doc_store = FakeDocStore()
    orch = RAGOrchestrator(
        searcher="SEARCHER",
        retrieval_service=retrieval,
        llm_client=FakeLLM(),
        prompt_builder=FakePromptBuilder(),
        doc_store=doc_store,
    )

    events = []
    async for ev in orch.query_stream(
        "问题", top_k=3, org_id="orgA", use_reranker=True, rerank_top_n=4, show_rewritten=True
    ):
        events.append(ev)

    # 检索参数与 searcher 正确转发
    call = retrieval.retrieve_calls[0]
    assert call["searcher"] == "SEARCHER"
    assert call["queries"] == ["问题", "子查询"]
    assert call["top_k"] == 3
    assert call["org_id"] == "orgA"
    assert call["use_reranker"] is True
    assert call["rerank_top_n"] == 4

    # SSE 事件顺序：rewriting → retrieving → token×2 → result
    assert "rewriting" in events[0]
    assert "retrieving" in events[1]
    assert "你好" in events[2] and "event: token" in events[2]
    assert "世界" in events[3]
    assert "event: result" in events[-1]
    assert '"sources"' in events[-1]
    # show_rewritten 且 >1 查询 → 返回改写结果
    assert "子查询" in events[-1]

    # 查询日志写入，含检索分块
    assert len(doc_store.saved_logs) == 1
    assert doc_store.saved_logs[0].retrieved_chunks[0]["chunk_id"] == "c1"


@pytest.mark.asyncio
async def test_query_stream_default_no_reranker():
    retrieval = FakeRetrievalService([_chunk("c1")])
    orch = RAGOrchestrator(
        searcher="SEARCHER",
        retrieval_service=retrieval,
        llm_client=FakeLLM(),
        prompt_builder=FakePromptBuilder(),
        doc_store=FakeDocStore(),
    )

    events = []
    async for ev in orch.query_stream("问题"):
        events.append(ev)

    # 默认不开启 reranker
    assert retrieval.retrieve_calls[0]["use_reranker"] is False
    assert retrieval.retrieve_calls[0]["rerank_top_n"] is None
    assert "event: result" in events[-1]
