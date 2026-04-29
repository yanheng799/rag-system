"""DashScope Embedding 封装"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


class Embedder:
    """DashScope text-embedding-v2 API 封装"""

    MAX_INPUT_LENGTH = 2048

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self._api_key = api_key or settings.dashscope_api_key
        self._model = model or settings.embedding_model
        self._base_url = base_url or settings.llm_base_url

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        批量向量化。

        DashScope OpenAI 兼容接口，每次最多 25 条。
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        batch_size = 25

        for i in range(0, len(texts), batch_size):
            batch = [t[:self.MAX_INPUT_LENGTH] for t in texts[i : i + batch_size]]
            response = self._call_api(batch)
            for item in response.get("data", []):
                all_embeddings.append(item["embedding"])

        logger.info("Embedding 完成: %d 条文本 → %d 维向量", len(texts), len(all_embeddings))
        return all_embeddings

    def embed_single(self, text: str) -> list[float]:
        """单条向量化"""
        results = self.embed([text])
        if not results:
            raise RuntimeError("Embedding 返回空结果")
        return results[0]

    def _call_api(self, texts: list[str]) -> dict:
        """调用 DashScope Embedding API"""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "input": texts,
        }

        with httpx.Client(timeout=60) as client:
            response = client.post(
                f"{self._base_url}/embeddings",
                headers=headers,
                json=payload,
            )
            if response.status_code != 200:
                logger.error(
                    "Embedding API 错误: status=%d, body=%s",
                    response.status_code,
                    response.text,
                )
            response.raise_for_status()
            return response.json()
