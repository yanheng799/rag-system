"""表格内容处理模块（Phase 1：规则路径透传 Markdown）"""

from __future__ import annotations

import logging

from ingestion.parsers.base import ParsedElement

logger = logging.getLogger(__name__)


class TableDescriber:
    """
    处理表格元素内容。
    Phase 1 直接透传 Parser 已生成的 Markdown 表格或 Excel 格式文本。
    """

    def describe(self, elem: ParsedElement) -> str:
        """返回表格内容文本（Markdown 或 Excel 格式）"""
        content = elem.content
        if not content or not content.strip():
            return ""
        return content.strip()
