"""LLM 客户端封装（DashScope Qwen）"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Generator

import httpx

from src.config.settings import settings

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """LLM 客户端抽象基类"""

    @abstractmethod
    def complete(self, messages: list[dict], stream: bool = False) -> str | Generator: ...


class QwenClient(LLMClient):
    """DashScope OpenAI 兼容接口客户端"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.1,
        stream: bool | None = None,
    ):
        self._api_key = api_key or settings.dashscope_api_key
        self._model = model or settings.llm_model
        self._base_url = base_url or settings.llm_base_url
        self._timeout = timeout or settings.llm_timeout
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._default_stream = stream if stream is not None else settings.llm_stream

    def complete(self, messages: list[dict], stream: bool | None = None) -> str | Generator:
        """
        调用 LLM 生成回答。

        stream=True 时返回 Generator，逐 token yield。
        未指定 stream 时使用构造时的默认值（settings.llm_stream）。
        """
        use_stream = stream if stream is not None else self._default_stream
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": messages,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "stream": use_stream,
        }

        if use_stream:
            return self._stream_call(headers, payload)
        return self._sync_call(headers, payload)

    def _sync_call(self, headers: dict, payload: dict) -> str:
        """同步调用"""
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            logger.info("LLM 响应完成: %d 字符", len(content))
            return content

    def _stream_call(self, headers: dict, payload: dict) -> Generator:
        """流式调用，逐 token 返回"""
        with (
            httpx.Client(timeout=self._timeout) as client,
            client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response,
        ):
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                import json

                try:
                    chunk = json.loads(data_str)
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
