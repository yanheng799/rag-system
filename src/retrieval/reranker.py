"""Reranker 客户端 — 调用自部署的 bge-reranker-large 推理服务"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from src.config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """单条重排序结果"""

    index: int
    relevance_score: float


class RerankerClient:
    """调用 /v1/rerank API 的客户端"""

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int = 30,
    ):
        self._api_url = api_url or settings.rerank_api_url
        self._api_key = api_key or settings.rerank_api_key
        self._model = model or settings.rerank_model
        self._timeout = timeout

    def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int = 5,
    ) -> list[RerankResult]:
        """
        调用 rerank API，返回按 relevance_score 降序排列的结果。

        失败时返回空列表并记录警告（降级容错）。
        """
        if not documents:
            return []

        try:
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            payload = {
                "model": self._model,
                "query": query,
                "documents": documents,
                "top_n": min(top_n, len(documents)),
                "return_documents": False,
            }

            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(self._api_url, json=payload, headers=headers)
                resp.raise_for_status()

            data = resp.json()
            results = []
            for item in data.get("results", []):
                results.append(
                    RerankResult(
                        index=item["index"],
                        relevance_score=item["relevance_score"],
                    )
                )
            logger.info(
                "Rerank 完成: query='%s', docs=%d, top_n=%d, scores=%s",
                query[:50],
                len(documents),
                top_n,
                [round(r.relevance_score, 4) for r in results[:5]],
            )
            return results

        except Exception:
            logger.warning("Reranker 调用失败，降级返回原始排序", exc_info=True)
            return []
