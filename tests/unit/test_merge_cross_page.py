"""跨页/跨列表格合并测试 — merge_cross_page 模块"""

from src.ingestion.chunkers.merge_cross_page import (
    merge_cross_column_tables,
    merge_cross_page_tables,
)
from src.ingestion.parsers.base import ParsedElement


def _make_md_table(headers: list[str], rows: list[list[str]]) -> str:
    """生成 Markdown 表格"""
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


class TestMergeCrossPage:
    """跨页表格合并"""

    def test_cross_page_tables_merged(self):
        """跨页表格应合并为一个元素"""
        table_a = ParsedElement(
            elem_type="table",
            content=_make_md_table(["A", "B"], [["1", "2"], ["3", "4"]]),
            page=0,
            bbox=(50, 700, 500, 842),
        )
        table_b = ParsedElement(
            elem_type="table",
            content=_make_md_table(["A", "B"], [["5", "6"], ["7", "8"]]),
            page=1,
            bbox=(50, 0, 500, 100),
        )
        page_sizes = {0: (595, 842), 1: (595, 842)}
        result = merge_cross_page_tables([table_a, table_b], page_sizes)
        assert len(result) == 1
        data_lines = [
            line for line in result[0].content.split("\n") if line.strip().startswith("|") and "---" not in line
        ]
        assert len(data_lines) == 5

    def test_non_adjacent_pages_not_merged(self):
        """不相邻页的表格不应合并"""
        table_a = ParsedElement(
            elem_type="table",
            content=_make_md_table(["A"], [["1"]]),
            page=0,
            bbox=(50, 700, 500, 842),
        )
        table_b = ParsedElement(
            elem_type="table",
            content=_make_md_table(["A"], [["2"]]),
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
            content=_make_md_table(["A", "B"], [["1", "2"]]),
            page=0,
            bbox=(50, 700, 500, 842),
        )
        table_b = ParsedElement(
            elem_type="table",
            content=_make_md_table(["A", "B", "C"], [["3", "4", "5"]]),
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
            content=_make_md_table(["A"], [["1"]]),
            page=0,
            bbox=(50, 200, 500, 400),
        )
        table_b = ParsedElement(
            elem_type="table",
            content=_make_md_table(["A"], [["2"]]),
            page=1,
            bbox=(50, 0, 500, 100),
        )
        page_sizes = {0: (595, 842), 1: (595, 842)}
        result = merge_cross_page_tables([table_a, table_b], page_sizes)
        assert len(result) == 2

    def test_cross_page_continuation_first_row_kept(self):
        """续页不重复表头时，续表首行(真实数据)必须保留，不得当表头丢弃"""
        table_a = ParsedElement(
            elem_type="table",
            content=_make_md_table(["塔型", "数量"], [["J1", "1"], ["J2", "2"]]),
            page=0,
            bbox=(50, 700, 500, 842),
        )
        # 续表首行是数据 J3，并非重复主表表头
        table_b = ParsedElement(
            elem_type="table",
            content=_make_md_table(["J3", "3"], [["J4", "4"]]),
            page=1,
            bbox=(50, 0, 500, 100),
        )
        page_sizes = {0: (595, 842), 1: (595, 842)}
        result = merge_cross_page_tables([table_a, table_b], page_sizes)
        assert len(result) == 1
        data_lines = [
            line for line in result[0].content.split("\n") if line.strip().startswith("|") and "---" not in line
        ]
        # 期望：主表表头 + J1,J2 + 续表 J3,J4 = 5 行
        assert len(data_lines) == 5
        flat = " ".join(data_lines)
        assert "J3" in flat  # 续表首行(数据)保留
        assert "J4" in flat

    def test_cross_page_repeated_header_dropped(self):
        """续页重复表头时，续表表头行应去重，整表表头只出现一次"""
        table_a = ParsedElement(
            elem_type="table",
            content=_make_md_table(["A", "B"], [["1", "2"]]),
            page=0,
            bbox=(50, 700, 500, 842),
        )
        table_b = ParsedElement(
            elem_type="table",
            content=_make_md_table(["A", "B"], [["3", "4"]]),  # 首行重复主表表头
            page=1,
            bbox=(50, 0, 500, 100),
        )
        page_sizes = {0: (595, 842), 1: (595, 842)}
        result = merge_cross_page_tables([table_a, table_b], page_sizes)
        data_lines = [
            line for line in result[0].content.split("\n") if line.strip().startswith("|") and "---" not in line
        ]
        # 表头只出现一次：A|B, 1|2, 3|4 = 3 行
        assert len(data_lines) == 3
        assert sum(1 for ln in data_lines if ln.strip() == "| A | B |") == 1


class TestMergeCrossColumn:
    """跨列表格合并"""

    def test_cross_column_tables_merged(self):
        """同页左右两个表格应合并"""
        table_left = ParsedElement(
            elem_type="table",
            content=_make_md_table(["A", "B"], [["1", "2"]]),
            page=0,
            bbox=(50, 100, 400, 200),
        )
        table_right = ParsedElement(
            elem_type="table",
            content=_make_md_table(["A", "B"], [["3", "4"]]),
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
            content=_make_md_table(["A"], [["1"]]),
            page=0,
            bbox=(50, 100, 400, 200),
        )
        table_right = ParsedElement(
            elem_type="table",
            content=_make_md_table(["A"], [["2"]]),
            page=0,
            bbox=(450, 500, 800, 600),
        )
        page_sizes = {0: (842, 595)}
        result = merge_cross_column_tables([table_left, table_right], page_sizes)
        assert len(result) == 2

    def test_cross_column_right_first_row_kept(self):
        """右表首行非重复表头时(真实数据)，合并后应保留"""
        table_left = ParsedElement(
            elem_type="table",
            content=_make_md_table(["项", "值"], [["a", "1"]]),
            page=0,
            bbox=(50, 100, 400, 200),
        )
        table_right = ParsedElement(
            elem_type="table",
            content=_make_md_table(["b", "2"], [["c", "3"]]),  # 首行是数据
            page=0,
            bbox=(450, 100, 800, 200),
        )
        page_sizes = {0: (842, 595)}
        result = merge_cross_column_tables([table_left, table_right], page_sizes)
        assert len(result) == 1
        data_lines = [
            line for line in result[0].content.split("\n") if line.strip().startswith("|") and "---" not in line
        ]
        flat = " ".join(data_lines)
        assert "b" in flat  # 右表首行(数据)保留
        assert "c" in flat
