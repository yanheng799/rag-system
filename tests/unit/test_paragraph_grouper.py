"""段落分组测试 — paragraph_grouper 模块"""

from src.ingestion.chunkers.paragraph_grouper import (
    detect_chunk_type,
    group_elements_by_paragraph,
    is_heading_element,
    is_new_paragraph_boundary,
)
from src.ingestion.parsers.base import ParsedElement


class TestHeadingElement:
    """标题元素判断"""

    def test_elem_type_title(self):
        elem = ParsedElement(elem_type="title", content="任何文字", page=0)
        assert is_heading_element(elem) is True

    def test_elem_type_text_but_heading_pattern(self):
        elem = ParsedElement(elem_type="text", content="第三章 概述", page=0)
        assert is_heading_element(elem) is True

    def test_elem_type_text_normal(self):
        elem = ParsedElement(elem_type="text", content="普通文字", page=0)
        assert is_heading_element(elem) is False


class TestParagraphBoundary:
    """段落边界判断"""

    def test_empty_group_is_boundary(self):
        elem = ParsedElement(elem_type="text", content="hello", page=0)
        assert is_new_paragraph_boundary(elem, []) is True

    def test_title_triggers_boundary(self):
        """标题始终触发段落边界"""
        elem = ParsedElement(elem_type="title", content="Φ杆", page=0, bbox=(0, 20, 100, 30))
        group = [ParsedElement(elem_type="text", content="上文", page=0, bbox=(0, 0, 100, 10))]
        assert is_new_paragraph_boundary(elem, group) is True

    def test_title_without_number_triggers_boundary(self):
        """无编号标题仍触发边界"""
        elem = ParsedElement(elem_type="title", content="安装和拆卸", page=0)
        group = [ParsedElement(elem_type="text", content="一些内容", page=0)]
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

    def test_gap_after_heading_is_not_boundary(self):
        """标题后的大间距不拆分"""
        group = [ParsedElement(elem_type="title", content="标题", page=0, bbox=(0, 0, 100, 10))]
        elem = ParsedElement(elem_type="text", content="内容", page=0, bbox=(0, 50, 100, 60))
        assert is_new_paragraph_boundary(elem, group) is False


class TestGroupByParagraph:
    """段落分组"""

    def test_empty_input(self):
        assert group_elements_by_paragraph([]) == []

    def test_single_element(self):
        elements = [ParsedElement(elem_type="text", content="hello", page=0)]
        result = group_elements_by_paragraph(elements)
        assert len(result) == 1
        assert len(result[0][0]) == 1

    def test_title_merges_with_following_content(self):
        """标题与后续内容合并在同一组"""
        elements = [
            ParsedElement(elem_type="text", content="文字1", page=0, bbox=(0, 0, 100, 10)),
            ParsedElement(elem_type="title", content="标题", page=0, bbox=(0, 30, 100, 40)),
            ParsedElement(elem_type="text", content="文字2", page=0, bbox=(0, 42, 100, 50)),
        ]
        result = group_elements_by_paragraph(elements, max_chunk_size=0)
        assert len(result) == 2
        assert result[1][0][0].content == "标题"
        assert result[1][0][1].content == "文字2"

    def test_heading_pattern_merges_with_content(self):
        """正则匹配的标题也与后续内容合并"""
        elements = [
            ParsedElement(elem_type="text", content="第三章 设计", page=0, bbox=(0, 0, 100, 10)),
            ParsedElement(elem_type="text", content="正文内容", page=0, bbox=(0, 12, 100, 20)),
        ]
        result = group_elements_by_paragraph(elements, max_chunk_size=0)
        assert len(result) == 1
        assert result[0][0][0].content == "第三章 设计"

    def test_bare_number_heading_not_orphaned(self):
        """"数字+空格"格式标题(is_title 但非严格编号)不应孤立，需与后续正文合并。

        回归用例：塔位明细表 PDF 中 "6 导地线型号" 这类标题 elem_type=title，
        但 is_section_heading 返回 False（不匹配 1.1/第三章 等严格编号）。
        标题行较短(x1=300 < 正文右边界 455-30)会触发段末短行规则，使阶段1
        将标题与正文切到不同组；此时须由孤立标题合并逻辑把标题并回正文组。
        若用 is_section_heading 判定标题，会漏判此类标题，令标题与正文分离、
        检索时等同于标题丢失。
        """
        elements = [
            ParsedElement(elem_type="title", content="6 导地线型号", page=0, bbox=(140, 336, 300, 357)),
            ParsedElement(
                elem_type="text", content="导线采用钢芯铝绞线，地线采用光缆。", page=0, bbox=(140, 364, 455, 381)
            ),
        ]
        result = group_elements_by_paragraph(elements, max_chunk_size=0)
        assert len(result) == 1
        group = result[0][0]
        assert group[0].is_title
        assert any(not e.is_title for e in group)

    def test_table_note_rejoins_table_group(self):
        """表格的孤立注释（注：…）跨页分离后，应归并回前一个含表格的组。

        回归：表6-1 的"注：参数参照…"跨页落到下一页顶部，被切到独立段落组，
        导致表格 chunk 的 full_text 看不到注释。
        """
        elements = [
            ParsedElement(elem_type="text", content="表X 参数表", page=0, bbox=(0, 0, 100, 10)),
            ParsedElement(
                elem_type="table", content="| a | b |\n|---|---|\n| 1 | 2 |", page=0, bbox=(0, 11, 100, 40)
            ),
            ParsedElement(elem_type="text", content="注：参数以招标为准。", page=1, bbox=(0, 0, 100, 10)),
        ]
        result = group_elements_by_paragraph(elements, max_chunk_size=0)
        note_groups = [g for g, _ in result if any(e.content.startswith("注") for e in g)]
        assert len(note_groups) == 1
        assert any(e.is_table for e in note_groups[0])

    def test_table_note_follows_table_when_split(self):
        """大表格触发拆分时，其后的注释应跟随表格，不被拆到独立子组。

        回归：表10.2-2 表格本身超 max_chunk_size 单独成组，其后的"注：…"
        被拆到不含表格的独立 chunk，导致表格 chunk full_text 丢失注释。
        """
        big_table = "| a | b |\n|---|---|\n" + "".join(f"| {i} | {i} |\n" for i in range(120))
        elements = [
            ParsedElement(elem_type="table", content=big_table, page=0, bbox=(0, 0, 100, 500)),
            ParsedElement(elem_type="text", content="注：参数以招标为准。", page=0, bbox=(0, 510, 100, 520)),
        ]
        result = group_elements_by_paragraph(elements, max_chunk_size=500)
        for group, _ in result:
            if any(e.content.startswith("注") for e in group):
                assert any(e.is_table for e in group)

    def test_mixed_text_and_table(self):
        elements = [
            ParsedElement(elem_type="text", content="说明文字", page=0, bbox=(0, 0, 100, 10)),
            ParsedElement(elem_type="table", content="表格数据", page=0, bbox=(0, 11, 100, 40)),
        ]
        result = group_elements_by_paragraph(elements)
        assert len(result) == 1
        assert detect_chunk_type(result[0][0]) == "mixed"

    def test_table_only_group(self):
        elements = [
            ParsedElement(elem_type="table", content="表格数据", page=0, bbox=(0, 0, 100, 40)),
        ]
        result = group_elements_by_paragraph(elements)
        assert len(result) == 1
        assert detect_chunk_type(result[0][0]) == "table"

    def test_text_only_group(self):
        elements = [
            ParsedElement(elem_type="text", content="文字1", page=0, bbox=(0, 0, 100, 10)),
            ParsedElement(elem_type="text", content="文字2", page=0, bbox=(0, 11, 100, 20)),
        ]
        result = group_elements_by_paragraph(elements)
        assert len(result) == 1
        assert detect_chunk_type(result[0][0]) == "text"


class TestMaxChunkSize:
    """最大分块限制"""

    def test_oversized_group_is_split(self):
        """超长文本被拆分"""
        elements = [
            ParsedElement(elem_type="text", content="a" * 500, page=0, bbox=(0, 0, 100, 10)),
            ParsedElement(elem_type="text", content="b" * 500, page=0, bbox=(0, 11, 100, 20)),
            ParsedElement(elem_type="text", content="c" * 500, page=0, bbox=(0, 21, 100, 30)),
        ]
        result = group_elements_by_paragraph(elements, max_chunk_size=1024)
        assert len(result) > 1
        for group, _gid in result:
            size = sum(len(e.content) for e in group)
            assert size <= 1536

    def test_small_group_not_split(self):
        """小文本不被拆分"""
        elements = [
            ParsedElement(elem_type="text", content="短文本", page=0, bbox=(0, 0, 100, 10)),
            ParsedElement(elem_type="text", content="短文本2", page=0, bbox=(0, 11, 100, 20)),
        ]
        result = group_elements_by_paragraph(elements, max_chunk_size=1024)
        assert len(result) == 1

    def test_single_large_element_in_own_group(self):
        """单个超大元素单独成组"""
        elements = [
            ParsedElement(elem_type="table", content="x" * 2000, page=0, bbox=(0, 0, 100, 40)),
        ]
        result = group_elements_by_paragraph(elements, max_chunk_size=1024)
        assert len(result) == 1
        assert len(result[0][0]) == 1

    def test_heading_not_orphaned(self):
        """标题不会被孤立"""
        elements = [
            ParsedElement(elem_type="title", content="标题", page=0, bbox=(0, 0, 100, 10)),
            ParsedElement(elem_type="text", content="a" * 500, page=0, bbox=(0, 12, 100, 20)),
            ParsedElement(elem_type="text", content="b" * 600, page=0, bbox=(0, 22, 100, 30)),
        ]
        result = group_elements_by_paragraph(elements, max_chunk_size=1024)
        for group, _gid in result:
            if any(e.is_title for e in group):
                assert len(group) > 1


class TestDetectChunkType:
    """分块类型检测"""

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


class TestCrossPageParagraph:
    """跨页段落合并"""

    def test_page_continuation_merged(self):
        """页底→页顶的连续文本应合并"""
        elements = [
            ParsedElement(elem_type="text", content="页底文字", page=0, bbox=(0, 780, 100, 842)),
            ParsedElement(elem_type="text", content="页顶续文", page=1, bbox=(0, 0, 100, 50)),
        ]
        page_sizes = {0: (595, 842), 1: (595, 842)}
        result = group_elements_by_paragraph(elements, max_chunk_size=0, page_sizes=page_sizes)
        assert len(result) == 1
        assert result[0][0][0].content == "页底文字"
        assert result[0][0][1].content == "页顶续文"

    def test_table_across_page_still_split(self):
        """表格跨页仍应拆分"""
        elements = [
            ParsedElement(elem_type="table", content="表格", page=0, bbox=(0, 780, 100, 842)),
            ParsedElement(elem_type="text", content="续文", page=1, bbox=(0, 0, 100, 50)),
        ]
        page_sizes = {0: (595, 842), 1: (595, 842)}
        result = group_elements_by_paragraph(elements, max_chunk_size=0, page_sizes=page_sizes)
        assert len(result) == 2

    def test_without_page_sizes_still_split(self):
        """没有 page_sizes 时仍按原逻辑拆分"""
        elements = [
            ParsedElement(elem_type="text", content="页底文字", page=0, bbox=(0, 780, 100, 842)),
            ParsedElement(elem_type="text", content="页顶续文", page=1, bbox=(0, 0, 100, 50)),
        ]
        result = group_elements_by_paragraph(elements, max_chunk_size=0)
        assert len(result) == 2
