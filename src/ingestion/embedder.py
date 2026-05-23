"""Embedding 封装，支持 OpenAI 兼容接口（本地模型 / DashScope 可配置切换）"""

from __future__ import annotations

import logging

import httpx

from src.config.settings import settings

logger = logging.getLogger(__name__)


class Embedder:
    """OpenAI 兼容 Embedding API 封装，通过 .env 配置切换本地模型或云端模型"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        query_prefix: str | None = None,
        max_input_length: int | None = None,
    ):
        self._api_key = api_key or settings.embedding_api_key
        self._model = model or settings.embedding_model
        self._base_url = base_url or settings.embedding_base_url
        self._query_prefix = (
            query_prefix if query_prefix is not None else settings.embedding_query_prefix
        )
        self._max_input_length = max_input_length or settings.embedding_max_input_length

    def embed_for_index(self, texts: list[str]) -> list[list[float]]:
        """批量向量化（入库场景，不加前缀）"""
        return self._embed(texts)

    def embed_for_query(self, text: str) -> list[float]:
        """查询向量化（检索场景，加前缀）"""
        if self._query_prefix:
            text = f"{self._query_prefix}{text}"
        results = self._embed([text])
        if not results:
            raise RuntimeError("Embedding 返回空结果")
        return results[0]

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化（兼容旧调用，等同于 embed_for_index）"""
        return self._embed(texts)

    def embed_single(self, text: str) -> list[float]:
        """单条向量化（兼容旧调用，等同于 embed_for_query）"""
        return self.embed_for_query(text)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化内部实现"""
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        batch_size = settings.embedding_batch_size

        for i in range(0, len(texts), batch_size):
            batch = [t[: self._max_input_length] for t in texts[i : i + batch_size]]
            response = self._call_api(batch)
            for item in response.get("data", []):
                all_embeddings.append(item["embedding"])

        logger.info("Embedding 完成: %d 条文本 → %d 维向量", len(texts), len(all_embeddings))
        return all_embeddings

    def _call_api(self, texts: list[str]) -> dict:
        """调用 Embedding API（OpenAI 兼容接口）"""
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
