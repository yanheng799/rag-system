"""表格语义描述生成模块（Phase 1 仅规则路径）"""

from __future__ import annotations

import logging

from ingestion.parsers.base import ParsedElement

logger = logging.getLogger(__name__)


class TableDescriber:
    """
    为表格生成自然语言语义描述，用于向量化检索。
    Phase 1 所有表格走规则描述路径。
    """

    def describe(self, elem: ParsedElement) -> str:
        """为表格元素生成语义描述"""
        return self._describe_with_rules(elem)

    def _describe_with_rules(self, elem: ParsedElement) -> str:
        """
        规则提取：从表格内容生成"列名:值"格式的自然语言描述。

        输入表格 content 格式（来自 Parser）：
            表头1 | 表头2 | 表头3
            值1   | 值2   | 值3
            ...
        """
        content = elem.content
        if not content or not content.strip():
            return ""

        lines = [line.strip() for line in content.split("\n") if line.strip()]
        if not lines:
            return ""

        # 尝试解析表格
        # 对于 Excel Parser 直接产生的"列名:值"格式，直接返回
        if any(line.startswith("工作表:") for line in lines):
            return content

        # 对于 PDF/Word Parser 产生的 "|" 分隔格式
        rows = []
        for line in lines:
            cells = [c.strip() for c in line.split("|")]
            cells = [c for c in cells if c]  # 去除空值
            if cells:
                rows.append(cells)

        if len(rows) < 2:
            return content

        headers = rows[0]
        descriptions = []

        col_names = "、".join(headers)
        descriptions.append(f"表格共{len(headers)}列：{col_names}。")

        for row in rows[1:]:
            parts = []
            for idx, value in enumerate(row):
                if value and idx < len(headers):
                    col_name = headers[idx]
                    parts.append(f"{col_name}{value}")
            if parts:
                descriptions.append("，".join(parts) + "。")

        result = "".join(descriptions)
        logger.debug("表格规则描述生成: %d 行 → %d 字符", len(rows), len(result))
        return result
