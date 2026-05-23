"""查询改写器：通过 LLM 生成多个子查询，扩展检索覆盖面"""

from __future__ import annotations

import json
import logging

from src.config.settings import settings
from src.orchestration.llm_client import LLMClient

logger = logging.getLogger(__name__)

REWRITE_SYSTEM_PROMPT = """你是一个查询改写助手。你的任务是将用户的原始问题改写为多个不同角度的搜索查询，以帮助检索到更多相关文档。

要求：
- 生成恰好 {count} 个不同角度的查询
- 保持原意，但使用不同的表述、关键词、同义词
- 可以从更宽泛或更具体的视角提问
- 只返回 JSON 数组，不要任何其他文字
- 示例格式：["查询1", "查询2", "查询3"]"""


class QueryRewriter:
    """通过 LLM 将原始查询扩展为多个子查询"""

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def rewrite(self, question: str) -> list[str]:
        """
        将原始问题改写为多个子查询。

        返回 [原始问题, 子查询1, 子查询2, ...]。
        如果改写失败（LLM 错误或解析失败），fallback 为仅返回原始问题。
        """
        count = settings.query_rewrite_count
        system_prompt = REWRITE_SYSTEM_PROMPT.format(count=count)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]

        try:
            raw = self._llm.complete(messages)
            sub_queries = self._parse_response(raw)
            if not sub_queries:
                logger.warning("查询改写返回空结果，fallback 为原始问题")
                return [question]

            result = [question] + sub_queries[:count]
            logger.info("查询改写: 原始='%s' → %d 个查询: %s", question[:30], len(result), result)
            return result
            return result
        except Exception:
            logger.warning("查询改写失败，fallback 为原始问题", exc_info=True)
            return [question]

    def _parse_response(self, raw: str) -> list[str]:
        """解析 LLM 返回的 JSON 数组"""
        text = raw.strip()

        # 尝试直接解析
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return [str(q).strip() for q in result if str(q).strip()]
        except json.JSONDecodeError:
            pass

        # 尝试提取 markdown 代码块中的 JSON
        if "```" in text:
            start = text.find("[")
            end = text.rfind("]") + 1
            if start != -1 and end > start:
                try:
                    result = json.loads(text[start:end])
                    if isinstance(result, list):
                        return [str(q).strip() for q in result if str(q).strip()]
                except json.JSONDecodeError:
                    pass

        return []
