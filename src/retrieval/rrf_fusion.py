"""RRF（Reciprocal Rank Fusion）融合算法"""

from __future__ import annotations

from src.models.chunks import RetrievedChunk
from src.config.settings import settings


def rrf_fuse(
    vector_chunks: list[RetrievedChunk],
    bm25_chunks: list[RetrievedChunk],
    rrf_k: int | None = None,
) -> list[RetrievedChunk]:
    """
    使用 RRF 算法融合向量检索和 BM25 检索结果。

    公式: score(d) = 1/(k + rank_vector) + 1/(k + rank_bm25)
    """
    if rrf_k is None:
        rrf_k = settings.rrf_k

    score_map: dict[str, dict] = {}

    for rank, chunk in enumerate(vector_chunks, 1):
        cid = chunk.metadata.chunk_id
        score_map[cid] = {
            "chunk": chunk,
            "vector_score": chunk.score,
            "bm25_score": 0.0,
            "vector_rank": rank,
            "bm25_rank": None,
        }

    for rank, chunk in enumerate(bm25_chunks, 1):
        cid = chunk.metadata.chunk_id
        if cid in score_map:
            score_map[cid]["bm25_score"] = chunk.score
            score_map[cid]["bm25_rank"] = rank
        else:
            score_map[cid] = {
                "chunk": chunk,
                "vector_score": 0.0,
                "bm25_score": chunk.score,
                "vector_rank": None,
                "bm25_rank": rank,
            }

    results: list[RetrievedChunk] = []
    for entry in score_map.values():
        chunk = entry["chunk"]
        rrf_score = 0.0
        if entry["vector_rank"] is not None:
            rrf_score += 1.0 / (rrf_k + entry["vector_rank"])
        if entry["bm25_rank"] is not None:
            rrf_score += 1.0 / (rrf_k + entry["bm25_rank"])

        chunk.score = rrf_score
        chunk.vector_score = entry["vector_score"]
        chunk.bm25_score = entry["bm25_score"]
        results.append(chunk)

    results.sort(key=lambda c: c.score, reverse=True)
    return results
