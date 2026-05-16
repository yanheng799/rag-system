"""QaChunker 单元测试"""

import pytest

from src.ingestion.chunkers.strategies.qa_chunker import QaChunker
from src.ingestion.parsers.base import ParsedElement


def _table_elem(headers, rows, page=1, sheet_name=""):
    return ParsedElement(
        elem_type="table",
        content="",
        page=page,
        bbox=(0, 0, 0, 0),
        style={"sheet_name": sheet_name},
        raw={"headers": headers, "rows": rows},
    )


def _text_elem(content, page=1):
    return ParsedElement(
        elem_type="text",
        content=content,
        page=page,
        bbox=(0, 0, 0, 0),
    )


@pytest.fixture
def chunker():
    return QaChunker()


class TestQaChunkerTableRows:
    def test_each_row_becomes_chunk(self, chunker):
        headers = ["Q", "A"]
        rows = [["What is RAG?", "Retrieval-Augmented Generation"], ["What is LLM?", "Large Language Model"]]
        elem = _table_elem(headers, rows)

        result = chunker.chunk([elem], {}, "doc1")
        assert len(result) == 2
        for group, gid in result:
            assert len(group) == 1
            assert group[0].elem_type == "table"

    def test_row_content_format(self, chunker):
        headers = ["Name", "Age"]
        rows = [["Alice", "30"]]
        elem = _table_elem(headers, rows)

        result = chunker.chunk([elem], {}, "doc1")
        content = result[0][0][0].content
        assert "Name: Alice" in content
        assert "Age: 30" in content

    def test_sheet_name_prefix(self, chunker):
        headers = ["A"]
        rows = [["1"], ["2"]]
        elem = _table_elem(headers, rows, sheet_name="Sheet1")

        result = chunker.chunk([elem], {}, "doc1")
        assert "工作表: Sheet1" in result[0][0][0].content

    def test_group_id_empty(self, chunker):
        headers = ["A"]
        rows = [["1"], ["2"], ["3"]]
        elem = _table_elem(headers, rows)

        result = chunker.chunk([elem], {}, "doc1")
        for group, gid in result:
            assert gid == ""


class TestQaChunkerMixed:
    def test_non_table_preserved(self, chunker):
        text = _text_elem("Hello")
        table = _table_elem(["A"], [["1"]])
        title = ParsedElement(elem_type="title", content="Section", page=1, bbox=(0, 0, 0, 0))

        result = chunker.chunk([text, table, title], {}, "doc1")
        assert len(result) == 3
        assert result[0][0][0].elem_type == "text"
        assert result[1][0][0].elem_type == "table"
        assert result[2][0][0].elem_type == "title"

    def test_table_without_raw(self, chunker):
        elem = ParsedElement(elem_type="table", content="some content", page=1, bbox=(0, 0, 0, 0))
        result = chunker.chunk([elem], {}, "doc1")
        assert len(result) == 1
        assert result[0][0][0] is elem

    def test_empty_elements(self, chunker):
        result = chunker.chunk([], {}, "doc1")
        assert result == []

    def test_multiple_tables(self, chunker):
        t1 = _table_elem(["A"], [["1"], ["2"]])
        t2 = _table_elem(["X"], [["a"], ["b"], ["c"]])

        result = chunker.chunk([t1, t2], {}, "doc1")
        assert len(result) == 5  # 2 + 3 rows
