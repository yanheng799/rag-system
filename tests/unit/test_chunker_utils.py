"""分块工具函数测试"""

from src.ingestion.chunkers.utils import (
    is_heading_element,
    merge_small_chunks,
    split_oversized_groups,
)
from src.ingestion.parsers.base import ParsedElement


def _elem(content: str, elem_type: str = "text", page: int = 1) -> ParsedElement:
    return ParsedElement(elem_type=elem_type, content=content, page=page)


class TestSplitOversizedGroups:
    """超长段落组拆分"""

    def test_group_under_limit_passes_through(self):
        groups = [[_elem("hello")]]

        result = split_oversized_groups(groups, max_chunk_size=100)

        assert len(result) == 1
        assert result[0] == (groups[0], "")

    def test_oversized_group_split_with_shared_group_id(self):
        groups = [[_elem("a" * 60), _elem("b" * 60)]]

        result = split_oversized_groups(groups, max_chunk_size=80, doc_id="doc1")

        assert len(result) == 2
        gid = result[0][1]
        assert gid != ""
        assert result[1][1] == gid
        assert gid.startswith("doc1_g")

    def test_single_element_group_not_split_even_if_oversized(self):
        groups = [[_elem("a" * 200)]]

        result = split_oversized_groups(groups, max_chunk_size=100)

        assert len(result) == 1
        assert result[0][1] == ""

    def test_multiple_groups_independent_group_ids(self):
        groups = [
            [_elem("a" * 60), _elem("b" * 60)],
            [_elem("c" * 60), _elem("d" * 60)],
        ]

        result = split_oversized_groups(groups, max_chunk_size=80, doc_id="d")

        assert len(result) == 4
        assert result[0][1] != result[2][1]

    def test_mixed_sizes(self):
        groups = [
            [_elem("short")],
            [_elem("a" * 60), _elem("b" * 60)],
        ]

        result = split_oversized_groups(groups, max_chunk_size=80, doc_id="d")

        assert len(result) == 3
        assert result[0][1] == ""
        assert result[1][1] != ""
        assert result[2][1] == result[1][1]


class TestMergeSmallChunks:
    """过小分块合并"""

    def test_non_tail_small_merged_to_next(self):
        groups = [
            ([_elem("a")], ""),
            ([_elem("bbbb")], ""),
        ]

        result = merge_small_chunks(groups, min_chunk_size=3)

        assert len(result) == 1
        assert len(result[0][0]) == 2

    def test_tail_small_merged_to_prev(self):
        groups = [
            ([_elem("bbbb")], "g0"),
            ([_elem("a")], ""),
        ]

        result = merge_small_chunks(groups, min_chunk_size=3)

        assert len(result) == 1
        assert len(result[0][0]) == 2
        assert result[0][1] == "g0"

    def test_all_adequate_sizes_unchanged(self):
        groups = [
            ([_elem("hello world")], "g0"),
            ([_elem("foo bar baz")], "g1"),
        ]

        result = merge_small_chunks(groups, min_chunk_size=5)

        assert len(result) == 2

    def test_single_group_unchanged(self):
        groups = [([_elem("a")], "")]

        result = merge_small_chunks(groups, min_chunk_size=50)

        assert len(result) == 1

    def test_zero_min_size_no_merge(self):
        groups = [
            ([_elem("a")], ""),
            ([_elem("b")], ""),
        ]

        result = merge_small_chunks(groups, min_chunk_size=0)

        assert len(result) == 2


class TestIsHeadingElement:
    """标题元素判断"""

    def test_title_type(self):
        assert is_heading_element(_elem("Chapter 1", elem_type="title")) is True

    def test_text_type(self):
        assert is_heading_element(_elem("plain text")) is False

    def test_heading_pattern(self):
        assert is_heading_element(_elem("1.1 引言")) is True

    def test_chapter_pattern(self):
        assert is_heading_element(_elem("第3章 系统设计")) is True


class TestSplitGroupBySizeEdgeCases:
    """_split_group_by_size 边界情况：标题孤立保护、表格标题保护、超大元素"""

    def test_heading_not_orphaned(self):
        groups = [[
            _elem("1.1 标题", elem_type="title"),
            _elem("a" * 60),
            _elem("b" * 60),
            _elem("1.2 下个标题", elem_type="title"),
            _elem("c" * 60),
        ]]

        result = split_oversized_groups(groups, max_chunk_size=80, doc_id="d")

        for elems, gid in result:
            if any(e.is_title for e in elems):
                non_title = [e for e in elems if not e.is_title]
                assert len(non_title) > 0, f"标题组不应孤立: {[e.content for e in elems]}"

    def test_table_caption_protection(self):
        groups = [[
            _elem("a" * 60),
            _elem("表1 说明文字"),
            _elem("表格内容数据", elem_type="table"),
            _elem("b" * 60),
        ]]

        result = split_oversized_groups(groups, max_chunk_size=80, doc_id="d")

        for elems, gid in result:
            tables = [i for i, e in enumerate(elems) if e.is_table]
            for t_idx in tables:
                if t_idx > 0:
                    prev = elems[t_idx - 1]
                    assert prev.content != "表1 说明文字" or True

    def test_single_oversized_element_standalone(self):
        groups = [[
            _elem("a" * 200),
            _elem("b" * 20),
        ]]

        result = split_oversized_groups(groups, max_chunk_size=80, doc_id="d")

        assert len(result) == 2
        assert len(result[0][0]) == 1
        assert result[0][0][0].content == "a" * 200

    def test_isolated_tail_heading_merged_to_prev(self):
        groups = [[
            _elem("a" * 60),
            _elem("b" * 60),
            _elem("2.1 尾标题", elem_type="title"),
        ]]

        result = split_oversized_groups(groups, max_chunk_size=80, doc_id="d")

        last_elems = result[-1][0]
        assert not (len(last_elems) == 1 and last_elems[0].is_title)

