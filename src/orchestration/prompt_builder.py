"""Prompt 构建器：将检索结果和用户问题组装为 LLM Prompt"""

from __future__ import annotations

import logging

from src.models.chunks import RetrievedChunk

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个严谨的电力工程领域问答助手。
请严格根据以下提供的参考资料回答用户问题。
回答要求：
1. 只基于参考资料中的信息作答，不要编造内容
2. 如果参考资料中没有足够信息，请明确说明"根据现有资料无法回答"
3. 回答时引用来源，例如"根据《文档名》第X页的内容..."
4. 涉及数据时，准确引用原文中的数值"""


class PromptBuilder:
    """将检索结果和用户问题组装为 LLM Messages"""

    def build(self, question: str, chunks: list[RetrievedChunk]) -> list[dict]:
        """
        构建 messages 列表。

        参考资料格式：
        [来源{n} - {source} 第{page}页 - {chunk_type}]
        {element.content}  # image_url 不包含在内
        """
        context_parts = []
        for idx, chunk in enumerate(chunks, 1):
            header = f"[来源{idx} - {chunk.metadata.source} 第{chunk.metadata.page}页 - {chunk.metadata.chunk_type}]"
            # 只用 content，image_url 不进入 Prompt
            element_contents = []
            for elem in chunk.elements:
                element_contents.append(elem.content)
            body = "\n".join(element_contents)
            context_parts.append(f"{header}\n{body}")

        context = "\n\n".join(context_parts)
        user_message = f"参考资料：\n{context}\n\n问题：{question}"

        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]
