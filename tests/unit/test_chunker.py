"""段落边界识别模块测试"""

import pytest

from ingestion.chunkers.layout_detector import (
    detect_header_footer_zones,
    detect_page_layout,
    is_in_header_footer,
    reorder_elements_for_layout,
)
from ingestion.parsers.base import ParsedElement


class TestLayoutDetector:
    """排版检测测试 — 使用真实 PDF 文件"""

    def test_tower_detail_is_double(self):
        """塔位明细表应识别为双栏"""
        import fitz

        doc = fitz.open("test-files/2.351-SA06911S-D0102 第6施工标段塔位明细表.pdf")
        # 第2-4页应为双栏
        for pn in [2, 3, 4]:
            assert detect_page_layout(doc[pn]) == "double", f"Page {pn} should be double"
        doc.close()

    def test_design_doc_is_single(self):
        """设计交底文件首页/目录页应为单栏"""
        import fitz

        doc = fitz.open("test-files/10.设计交底文件.pdf")
        # 目录页（第3-7页）应识别为单栏
        for pn in [3, 4, 5, 6, 7]:
            assert detect_page_layout(doc[pn]) == "single", f"Page {pn} should be single"
        doc.close()

    def test_cover_page_is_single(self):
        """封面页（词数不足）应为单栏"""
        import fitz

        doc = fitz.open("test-files/2.351-SA06911S-D0102 第6施工标段塔位明细表.pdf")
        assert detect_page_layout(doc[0]) == "single"
        doc.close()

    def test_reorder_double_column(self):
        """双栏元素应按左列→右列重排"""
        elements = [
            ParsedElement(elem_type="text", content="右1", page=0, bbox=(600, 100, 800, 110)),
            ParsedElement(elem_type="text", content="左1", page=0, bbox=(100, 100, 300, 110)),
            ParsedElement(elem_type="text", content="右2", page=0, bbox=(600, 200, 800, 210)),
            ParsedElement(elem_type="text", content="左2", page=0, bbox=(100, 200, 300, 210)),
        ]
        result = reorder_elements_for_layout(elements, 1191, "double")
        assert [e.content for e in result] == ["左1", "左2", "右1", "右2"]

    def test_reorder_single_column_unchanged(self):
        """单栏模式下不重排"""
        elements = [
            ParsedElement(elem_type="text", content="A", page=0, bbox=(100, 100, 300, 110)),
            ParsedElement(elem_type="text", content="B", page=0, bbox=(100, 200, 300, 210)),
        ]
        result = reorder_elements_for_layout(elements, 595, "single")
        assert result == elements


class TestHeaderFooterDetection:
    """页眉页脚检测测试"""

    def test_tower_detail_has_header(self):
        """塔位明细表应检测到页眉"""
        import fitz

        doc = fitz.open("test-files/2.351-SA06911S-D0102 第6施工标段塔位明细表.pdf")
        zones = detect_header_footer_zones(doc)
        doc.close()
        assert len(zones) > 0
        # 应有页眉区间 (y < 50)
        assert any(z[0] < 50 for z in zones)

    def test_tower_detail_has_footer(self):
        """塔位明细表应检测到页脚"""
        import fitz

        doc = fitz.open("test-files/2.351-SA06911S-D0102 第6施工标段塔位明细表.pdf")
        zones = detect_header_footer_zones(doc)
        doc.close()
        # 应有页脚区间 (y > 700)
        assert any(z[0] > 700 for z in zones)

    def test_tower_detail_header_filtered(self):
        """解析后不应包含页眉内容"""
        from ingestion.parsers.pdf_parser import PDFParser

        parser = PDFParser()
        elements = parser.parse("test-files/2.351-SA06911S-D0102 第6施工标段塔位明细表.pdf")
        # 页眉 "千伏直流输电线路工程" 不应出现在解析结果中
        assert not any("千伏直流输电线路工程" in e.content for e in elements)

    def test_design_doc_no_false_positives(self):
        """设计交底文件不应误检页眉页脚"""
        import fitz

        doc = fitz.open("test-files/10.设计交底文件.pdf")
        zones = detect_header_footer_zones(doc)
        doc.close()
        assert len(zones) == 0

    def test_is_in_header_footer(self):
        zones = [(28, 44), (762, 778)]
        assert is_in_header_footer((100, 28, 300, 44), zones) is True
        assert is_in_header_footer((100, 762, 300, 778), zones) is True
        assert is_in_header_footer((100, 100, 300, 120), zones) is False


class TestTableMarkdownFormat:
    """表格 Markdown 格式测试"""

    def test_pdf_table_has_separator(self):
        """PDF 表格应包含 Markdown 分隔行 |---|"""
        from ingestion.parsers.pdf_parser import PDFParser

        parser = PDFParser()
        elements = parser.parse(
            "test-files/2.351-SA06911S-D0102 第6施工标段塔位明细表.pdf"
        )
        tables = [e for e in elements if e.is_table]
        assert len(tables) > 0
        for t in tables:
            # 分隔行应出现在表格内容中
            assert "---" in t.content, f"Table missing separator: {t.content[:60]}"

    def test_pdf_table_rows_start_with_pipe(self):
        """PDF 表格数据行应以 | 开头"""
        from ingestion.parsers.pdf_parser import PDFParser

        parser = PDFParser()
        elements = parser.parse(
            "test-files/2.351-SA06911S-D0102 第6施工标段塔位明细表.pdf"
        )
        tables = [e for e in elements if e.is_table]
        # 检查简单表格（前几个表格是单行表头，格式完整）
        for t in tables[:5]:
            lines = t.content.strip().split("\n")
            # 前 3 行（表头、分隔行、数据行）都应以 | 开头
            for line in lines[:3]:
                assert line.startswith("|"), f"Not markdown: {line[:60]}"

    def test_describer_passes_markdown_through(self):
        """TableDescriber 应透传 Markdown 内容"""
        from ingestion.table_processor.describer import TableDescriber

        describer = TableDescriber()
        md = "| 姓名 | 年龄 |\n|---|---|\n| 张三 | 25 |"
        elem = ParsedElement(elem_type="table", content=md, page=0)
        assert describer.describe(elem) == md

    def test_describer_passes_excel_format(self):
        """TableDescriber 应透传 Excel 格式"""
        from ingestion.table_processor.describer import TableDescriber

        describer = TableDescriber()
        excel = "工作表: Sheet1\n表头: A | B\nA: 1; B: 2"
        elem = ParsedElement(elem_type="table", content=excel, page=0)
        assert describer.describe(elem) == excel

    def test_describer_empty_content(self):
        """TableDescriber 处理空内容"""
        from ingestion.table_processor.describer import TableDescriber

        describer = TableDescriber()
        elem = ParsedElement(elem_type="table", content="", page=0)
        assert describer.describe(elem) == ""


from ingestion.chunkers.heading_patterns import (
    is_heading_by_pattern,
    is_heading_combined,
)
from ingestion.chunkers.paragraph_grouper import (
    detect_chunk_type,
    group_elements_by_paragraph,
    is_heading_element,
    is_new_paragraph_boundary,
)
from ingestion.parsers.base import ParsedElement


class TestHeadingPatterns:
    """标题正则匹配测试"""

    def test_chinese_chapter(self):
        assert is_heading_by_pattern("第三章 数据结构") is True

    def test_chinese_section(self):
        assert is_heading_by_pattern("第二节 算法分析") is True

    def test_chinese_part(self):
        assert is_heading_by_pattern("第一篇 概述") is True

    def test_chinese_clause(self):
        assert is_heading_by_pattern("第三条 适用范围") is True

    def test_numbered_section(self):
        assert is_heading_by_pattern("3.2 排序算法") is True

    def test_numbered_with_chinese_dot(self):
        assert is_heading_by_pattern("3、施工要求") is True

    def test_sub_numbered_section(self):
        assert is_heading_by_pattern("3.2.1 数据采集") is True

    def test_english_chapter(self):
        assert is_heading_by_pattern("Chapter 3: Methods") is True

    def test_english_section(self):
        assert is_heading_by_pattern("Section 3.2 Analysis") is True

    def test_normal_text_not_heading(self):
        assert is_heading_by_pattern("这是一段普通的正文内容") is False

    def test_long_text_not_heading(self):
        assert is_heading_by_pattern("第" + "x" * 101) is False

    def test_combined_style_font_size(self):
        assert is_heading_combined("普通文字", font_size=16, is_bold=False) is True

    def test_combined_style_bold(self):
        assert is_heading_combined("普通文字", font_size=12, is_bold=True) is True

    def test_combined_pattern(self):
        assert is_heading_combined("第三章 概述", font_size=10, is_bold=False) is True

    def test_combined_neither(self):
        assert is_heading_combined("普通文字", font_size=10, is_bold=False) is False


class TestHeadingElement:
    """标题元素判断测试"""

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
    """段落边界判断测试"""

    def test_empty_group_is_boundary(self):
        elem = ParsedElement(elem_type="text", content="hello", page=0)
        assert is_new_paragraph_boundary(elem, []) is True

    def test_title_does_not_split(self):
        """标题不再作为段落边界 — 标题与下方内容合并"""
        elem = ParsedElement(elem_type="title", content="标题", page=0, bbox=(0, 20, 100, 30))
        group = [ParsedElement(elem_type="text", content="上文", page=0, bbox=(0, 0, 100, 10))]
        # 标题紧跟上文（间距小），不拆分
        assert is_new_paragraph_boundary(elem, group) is False

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
        """标题后的大间距不拆分 — 标题吸收下方内容"""
        group = [ParsedElement(elem_type="title", content="标题", page=0, bbox=(0, 0, 100, 10))]
        elem = ParsedElement(elem_type="text", content="内容", page=0, bbox=(0, 50, 100, 60))
        assert is_new_paragraph_boundary(elem, group) is False


class TestGroupByParagraph:
    """段落分组测试"""

    def test_empty_input(self):
        assert group_elements_by_paragraph([]) == []

    def test_single_element(self):
        elements = [ParsedElement(elem_type="text", content="hello", page=0)]
        result = group_elements_by_paragraph(elements)
        assert len(result) == 1
        assert len(result[0]) == 1

    def test_title_merges_with_following_content(self):
        """标题与后续内容合并在同一组"""
        elements = [
            ParsedElement(elem_type="text", content="文字1", page=0, bbox=(0, 0, 100, 10)),
            ParsedElement(elem_type="title", content="标题", page=0, bbox=(0, 30, 100, 40)),
            ParsedElement(elem_type="text", content="文字2", page=0, bbox=(0, 42, 100, 50)),
        ]
        result = group_elements_by_paragraph(elements, max_chunk_size=0)
        # 文字1 → 标题(间距20px>15px，拆分)，标题+文字2合并
        assert len(result) == 2
        assert result[1][0].content == "标题"
        assert result[1][1].content == "文字2"

    def test_heading_pattern_merges_with_content(self):
        """正则匹配的标题也与后续内容合并"""
        elements = [
            ParsedElement(elem_type="text", content="第三章 设计", page=0, bbox=(0, 0, 100, 10)),
            ParsedElement(elem_type="text", content="正文内容", page=0, bbox=(0, 12, 100, 20)),
        ]
        result = group_elements_by_paragraph(elements, max_chunk_size=0)
        assert len(result) == 1
        assert result[0][0].content == "第三章 设计"

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


class TestMaxChunkSize:
    """最大分块限制测试"""

    def test_oversized_group_is_split(self):
        """超长文本被拆分"""
        elements = [
            ParsedElement(elem_type="text", content="a" * 500, page=0, bbox=(0, 0, 100, 10)),
            ParsedElement(elem_type="text", content="b" * 500, page=0, bbox=(0, 11, 100, 20)),
            ParsedElement(elem_type="text", content="c" * 500, page=0, bbox=(0, 21, 100, 30)),
        ]
        result = group_elements_by_paragraph(elements, max_chunk_size=1024)
        # 总共 1500 字符，应该被拆分为多个组
        assert len(result) > 1
        for group in result:
            size = sum(len(e.content) for e in group)
            assert size <= 1536  # 允许单个超限元素独占一组

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
        assert len(result[0]) == 1

    def test_heading_not_orphaned(self):
        """标题不会被孤立 — 至少包含一个后续元素"""
        elements = [
            ParsedElement(elem_type="title", content="标题", page=0, bbox=(0, 0, 100, 10)),
            ParsedElement(elem_type="text", content="a" * 500, page=0, bbox=(0, 12, 100, 20)),
            ParsedElement(elem_type="text", content="b" * 600, page=0, bbox=(0, 22, 100, 30)),
        ]
        result = group_elements_by_paragraph(elements, max_chunk_size=1024)
        # 不应出现只有标题的孤立组
        for group in result:
            if any(e.is_title for e in group):
                assert len(group) > 1


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


from ingestion.chunkers.merge_cross_page import (
    merge_cross_column_tables,
    merge_cross_page_tables,
)


class TestFullWidthTable:
    """全宽表格在双栏重排中的处理"""

    def test_full_width_table_not_split(self):
        """全宽表格应保持完整，不被分入左/右列"""
        elements = [
            ParsedElement(elem_type="text", content="左1", page=0, bbox=(100, 100, 300, 110)),
            ParsedElement(elem_type="table", content="表格", page=0, bbox=(50, 120, 1140, 200)),
            ParsedElement(elem_type="text", content="右1", page=0, bbox=(600, 100, 800, 110)),
        ]
        result = reorder_elements_for_layout(elements, 1191, "double")
        # 全宽表格宽度 1090 >= 1191 * 0.8 = 953，应被识别为全宽
        assert len(result) == 3
        # 全宽表格应在左1和右1之后（y=120 > 左1/右1 的 y=100）
        table_idx = next(i for i, e in enumerate(result) if e.content == "表格")
        left_idx = next(i for i, e in enumerate(result) if e.content == "左1")
        right_idx = next(i for i, e in enumerate(result) if e.content == "右1")
        assert table_idx > left_idx
        assert table_idx > right_idx

    def test_narrow_table_goes_to_column(self):
        """窄表格应正常分入左/右列"""
        elements = [
            ParsedElement(elem_type="table", content="窄表", page=0, bbox=(100, 100, 400, 150)),
        ]
        result = reorder_elements_for_layout(elements, 1191, "double")
        # 宽度 300 < 1191 * 0.8，应正常处理
        assert len(result) == 1

    def test_full_width_between_columns(self):
        """全宽元素在左右列元素之间按 y 排序"""
        elements = [
            ParsedElement(elem_type="text", content="左上", page=0, bbox=(100, 50, 300, 60)),
            ParsedElement(elem_type="text", content="右上", page=0, bbox=(600, 50, 800, 60)),
            ParsedElement(elem_type="table", content="全宽表", page=0, bbox=(50, 100, 1140, 200)),
            ParsedElement(elem_type="text", content="左下", page=0, bbox=(100, 250, 300, 260)),
            ParsedElement(elem_type="text", content="右下", page=0, bbox=(600, 250, 800, 260)),
        ]
        result = reorder_elements_for_layout(elements, 1191, "double")
        contents = [e.content for e in result]
        # 全宽表应在左上/右上之后、左下/右下之前
        fw_idx = contents.index("全宽表")
        assert contents.index("左上") < fw_idx
        assert contents.index("右上") < fw_idx
        assert contents.index("左下") > fw_idx
        assert contents.index("右下") > fw_idx


class TestMergeCrossPage:
    """跨页表格合并测试"""

    def _make_md_table(self, headers: list[str], rows: list[list[str]]) -> str:
        """生成 Markdown 表格"""
        lines = ["| " + " | ".join(headers) + " |"]
        lines.append("|" + "|".join("---" for _ in headers) + "|")
        for row in rows:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    def test_cross_page_tables_merged(self):
        """跨页表格应合并为一个元素"""
        table_a = ParsedElement(
            elem_type="table",
            content=self._make_md_table(["A", "B"], [["1", "2"], ["3", "4"]]),
            page=0,
            bbox=(50, 700, 500, 842),
        )
        table_b = ParsedElement(
            elem_type="table",
            content=self._make_md_table(["A", "B"], [["5", "6"], ["7", "8"]]),
            page=1,
            bbox=(50, 0, 500, 100),
        )
        page_sizes = {0: (595, 842), 1: (595, 842)}
        result = merge_cross_page_tables([table_a, table_b], page_sizes)
        assert len(result) == 1
        # 合并后应包含 4 行数据（不含表头）
        data_lines = [l for l in result[0].content.split("\n") if l.strip().startswith("|") and "---" not in l]
        # 1 表头行 + 4 数据行 = 5 行
        assert len(data_lines) == 5

    def test_non_adjacent_pages_not_merged(self):
        """不相邻页的表格不应合并"""
        table_a = ParsedElement(
            elem_type="table",
            content=self._make_md_table(["A"], [["1"]]),
            page=0,
            bbox=(50, 700, 500, 842),
        )
        table_b = ParsedElement(
            elem_type="table",
            content=self._make_md_table(["A"], [["2"]]),
            page=2,
            bbox=(50, 0, 500, 100),
        )
        page_sizes = {0: (595, 842), 1: (595, 842), 2: (595, 842)}
        result = merge_cross_page_tables([table_a, table_b], page_sizes)
        assert len(result) == 2

    def test_different_columns_not_merged(self):
        """列数不同的表格不应合并"""
        table_a = ParsedElement(
            elem_type="table",
            content=self._make_md_table(["A", "B"], [["1", "2"]]),
            page=0,
            bbox=(50, 700, 500, 842),
        )
        table_b = ParsedElement(
            elem_type="table",
            content=self._make_md_table(["A", "B", "C"], [["3", "4", "5"]]),
            page=1,
            bbox=(50, 0, 500, 100),
        )
        page_sizes = {0: (595, 842), 1: (595, 842)}
        result = merge_cross_page_tables([table_a, table_b], page_sizes)
        assert len(result) == 2

    def test_table_not_at_page_edge_not_merged(self):
        """不在页面边缘的表格不应合并"""
        table_a = ParsedElement(
            elem_type="table",
            content=self._make_md_table(["A"], [["1"]]),
            page=0,
            bbox=(50, 200, 500, 400),
        )
        table_b = ParsedElement(
            elem_type="table",
            content=self._make_md_table(["A"], [["2"]]),
            page=1,
            bbox=(50, 0, 500, 100),
        )
        page_sizes = {0: (595, 842), 1: (595, 842)}
        result = merge_cross_page_tables([table_a, table_b], page_sizes)
        assert len(result) == 2


class TestMergeCrossColumn:
    """跨列表格合并测试"""

    def _make_md_table(self, headers: list[str], rows: list[list[str]]) -> str:
        lines = ["| " + " | ".join(headers) + " |"]
        lines.append("|" + "|".join("---" for _ in headers) + "|")
        for row in rows:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    def test_cross_column_tables_merged(self):
        """同页左右两个表格应合并"""
        table_left = ParsedElement(
            elem_type="table",
            content=self._make_md_table(["A", "B"], [["1", "2"]]),
            page=0,
            bbox=(50, 100, 400, 200),
        )
        table_right = ParsedElement(
            elem_type="table",
            content=self._make_md_table(["A", "B"], [["3", "4"]]),
            page=0,
            bbox=(450, 100, 800, 200),
        )
        page_sizes = {0: (842, 595)}
        result = merge_cross_column_tables([table_left, table_right], page_sizes)
        assert len(result) == 1

    def test_different_y_not_merged(self):
        """y 坐标差距大的表格不应合并"""
        table_left = ParsedElement(
            elem_type="table",
            content=self._make_md_table(["A"], [["1"]]),
            page=0,
            bbox=(50, 100, 400, 200),
        )
        table_right = ParsedElement(
            elem_type="table",
            content=self._make_md_table(["A"], [["2"]]),
            page=0,
            bbox=(450, 500, 800, 600),
        )
        page_sizes = {0: (842, 595)}
        result = merge_cross_column_tables([table_left, table_right], page_sizes)
        assert len(result) == 2


class TestCrossPageParagraph:
    """跨页段落合并测试"""

    def test_page_continuation_merged(self):
        """页底→页顶的连续文本应合并"""
        elements = [
            ParsedElement(elem_type="text", content="页底文字", page=0, bbox=(0, 780, 100, 842)),
            ParsedElement(elem_type="text", content="页顶续文", page=1, bbox=(0, 0, 100, 50)),
        ]
        page_sizes = {0: (595, 842), 1: (595, 842)}
        result = group_elements_by_paragraph(elements, max_chunk_size=0, page_sizes=page_sizes)
        assert len(result) == 1
        assert result[0][0].content == "页底文字"
        assert result[0][1].content == "页顶续文"

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
