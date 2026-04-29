"""段落边界识别模块测试"""

import pytest

from ingestion.chunkers.paragraph_grouper import (
    detect_chunk_type,
    group_elements_by_paragraph,
    is_new_paragraph_boundary,
)
from ingestion.parsers.base import ParsedElement


class TestParagraphBoundary:
    """段落边界判断测试"""

    def test_empty_group_is_boundary(self):
        elem = ParsedElement(elem_type="text", content="hello", page=0)
        assert is_new_paragraph_boundary(elem, []) is True

    def test_title_is_boundary(self):
        elem = ParsedElement(elem_type="title", content="标题", page=0)
        group = [ParsedElement(elem_type="text", content="上文", page=0)]
        assert is_new_paragraph_boundary(elem, group) is True

    def test_same_page_close_position_not_boundary(self):
        group = [ParsedElement(elem_type="text", content="上文", page=0, bbox=(0, 0, 100, 10))]
        elem = ParsedElement(elem_type="text", content="下文", page=0, bbox=(0, 11, 100, 20))
        assert is_new_paragraph_boundary(elem, group) is False

    def test_different_page_is_boundary(self):
        group = [ParsedElement(elem_type="text", content="上文", page=0, bbox=(0, 0, 100, 10))]
        elem = ParsedElement(elem_type="text", content="下页", page=1, bbox=(0, 0, 100, 10))
        assert is_new_paragraph_boundary(elem, group) is True

    def test_large_vertical_gap_is_boundary(self):
        group = [ParsedElement(elem_type="text", content="上文", page=0, bbox=(0, 0, 100, 10))]
        elem = ParsedElement(elem_type="text", content="下文", page=0, bbox=(0, 50, 100, 60))
        assert is_new_paragraph_boundary(elem, group) is True


class TestGroupByParagraph:
    """段落分组测试"""

    def test_empty_input(self):
        assert group_elements_by_paragraph([]) == []

    def test_single_element(self):
        elements = [ParsedElement(elem_type="text", content="hello", page=0)]
        result = group_elements_by_paragraph(elements)
        assert len(result) == 1
        assert len(result[0]) == 1

    def test_title_splits_paragraph(self):
        elements = [
            ParsedElement(elem_type="text", content="文字1", page=0, bbox=(0, 0, 100, 10)),
            ParsedElement(elem_type="title", content="标题", page=0, bbox=(0, 20, 100, 30)),
            ParsedElement(elem_type="text", content="文字2", page=0, bbox=(0, 32, 100, 40)),
        ]
        result = group_elements_by_paragraph(elements)
        assert len(result) == 2  # 标题分隔

    def test_mixed_text_and_table(self):
        elements = [
            ParsedElement(elem_type="text", content="说明文字", page=0, bbox=(0, 0, 100, 10)),
            ParsedElement(elem_type="table", content="表格数据", page=0, bbox=(0, 11, 100, 40)),
        ]
        result = group_elements_by_paragraph(elements)
        assert len(result) == 1
        assert detect_chunk_type(result[0]) == "mixed"

    def test_table_only_group(self):
        elements = [
            ParsedElement(elem_type="table", content="表格数据", page=0, bbox=(0, 0, 100, 40)),
        ]
        result = group_elements_by_paragraph(elements)
        assert len(result) == 1
        assert detect_chunk_type(result[0]) == "table"

    def test_text_only_group(self):
        elements = [
            ParsedElement(elem_type="text", content="文字1", page=0, bbox=(0, 0, 100, 10)),
            ParsedElement(elem_type="text", content="文字2", page=0, bbox=(0, 11, 100, 20)),
        ]
        result = group_elements_by_paragraph(elements)
        assert len(result) == 1
        assert detect_chunk_type(result[0]) == "text"


class TestDetectChunkType:
    """分块类型检测测试"""

    def test_text_only(self):
        elements = [ParsedElement(elem_type="text", content="文字", page=0)]
        assert detect_chunk_type(elements) == "text"

    def test_table_only(self):
        elements = [ParsedElement(elem_type="table", content="表格", page=0)]
        assert detect_chunk_type(elements) == "table"

    def test_mixed(self):
        elements = [
            ParsedElement(elem_type="text", content="文字", page=0),
            ParsedElement(elem_type="table", content="表格", page=0),
        ]
        assert detect_chunk_type(elements) == "mixed"
