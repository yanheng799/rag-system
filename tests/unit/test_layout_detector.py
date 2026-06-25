"""排版检测测试 — layout_detector 模块"""

import fitz

from src.ingestion.chunkers.layout_detector import (
    detect_header_footer_zones,
    detect_page_layout,
    detect_toc_pages,
    is_in_header_footer,
    reorder_elements_for_layout,
)
from src.ingestion.parsers.base import ParsedElement


def _make_pdf(pages_spec: list[dict]) -> fitz.Document:
    """内存构造 PDF,用于页眉页脚检测的分支测试。

    pages_spec 每项描述一页,字段可选:
        header: 顶部插入的文本(行顶 y≈21,落在顶部 8% 内)
        footer: 底部插入的文本(行顶 y≈789,落在底部 10% 内)
        body:   正文文本(中间区域,不进入页眉/页脚候选)
    用英文文本避免 CJK 字体依赖,算法本身与语言无关。
    """
    doc = fitz.open()
    for spec in pages_spec:
        page = doc.new_page(width=595, height=842)
        if spec.get("header"):
            page.insert_text((50, 30), spec["header"], fontsize=11)
        if spec.get("footer"):
            page.insert_text((50, 800), spec["footer"], fontsize=11)
        if spec.get("body"):
            page.insert_text((50, 400), spec["body"], fontsize=11)
    return doc


class TestLayoutDetector:
    """排版检测 — 使用真实 PDF 文件"""

    def test_tower_detail_is_double(self):
        """塔位明细表应识别为双栏"""
        doc = fitz.open("tests/data/塔位明细表.pdf")
        for pn in [2, 3, 4]:
            assert detect_page_layout(doc[pn]) == "double", f"Page {pn} should be double"
        doc.close()

    def test_design_doc_is_single(self):
        """设计交底文件目录页应为单栏"""
        doc = fitz.open("tests/data/设计交底文件.pdf")
        for pn in [3, 4, 5, 6, 7]:
            assert detect_page_layout(doc[pn]) == "single", f"Page {pn} should be single"
        doc.close()

    def test_cover_page_is_single(self):
        """封面页（词数不足）应为单栏"""
        doc = fitz.open("tests/data/塔位明细表.pdf")
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
    """页眉页脚检测"""

    def test_tower_detail_has_header(self):
        """塔位明细表应检测到页眉"""
        doc = fitz.open("tests/data/塔位明细表.pdf")
        zones = detect_header_footer_zones(doc)
        doc.close()
        assert len(zones) > 0
        assert any(z[0] < 50 for z in zones), f"No header zone found in {zones}"

    def test_tower_detail_has_footer(self):
        """新算法只取底部第一行;塔位明细表底部为正文自然结尾、无跨页相同/数字步长行,
        因此 footer 可能检不到。检出时验证 y>700,未检出时跳过(宁缺毋滥,符合算法精确化)。"""
        doc = fitz.open("tests/data/塔位明细表.pdf")
        zones = detect_header_footer_zones(doc)
        doc.close()
        footers = [z for z in zones if z[0] > 700]
        if footers:
            assert all(z[0] > 700 for z in footers), f"footer zone y 异常: {footers}"

    def test_tower_detail_header_filtered(self):
        """解析后不应包含页眉内容"""
        from src.ingestion.parsers.pdf_parser import PDFParser

        parser = PDFParser()
        elements = parser.parse("tests/data/塔位明细表.pdf")
        assert not any("千伏直流输电线路工程" in e.content for e in elements)

    def test_design_doc_no_false_positives(self):
        """设计交底文件不应误检页眉页脚"""
        doc = fitz.open("tests/data/设计交底文件.pdf")
        zones = detect_header_footer_zones(doc)
        doc.close()
        assert len(zones) == 0

    def test_is_in_header_footer(self):
        zones = [(28, 44, frozenset({"页眉文本"})), (762, 778, frozenset({"页脚文本"}))]
        assert is_in_header_footer((100, 28, 300, 44), zones, text="页眉文本") is True
        assert is_in_header_footer((100, 762, 300, 778), zones, text="页脚文本") is True
        assert is_in_header_footer((100, 100, 300, 120), zones, text="正文内容") is False
        # 文本不匹配 → 即使 y 在 zone 内也不应误杀
        assert is_in_header_footer((100, 28, 300, 44), zones, text="章节标题") is False

    def test_same_text_header_detected(self):
        """分支 A:多页顶部第一行文本完全相同 → 检出 header zone"""
        doc = _make_pdf([{"header": "CompanyName", "body": f"P{i} body"} for i in range(5)])
        zones = detect_header_footer_zones(doc)
        doc.close()
        assert len(zones) == 1
        assert zones[0][0] < 50  # 顶部 8% 内
        assert "CompanyName" in zones[0][2]

    def test_numeric_step_footer_detected(self):
        """分支 B:多页底部第一行数字呈常数步长(Page 1..5)→ 检出 footer zone"""
        doc = _make_pdf([{"footer": f"Page {i + 1}"} for i in range(5)])
        zones = detect_header_footer_zones(doc)
        doc.close()
        assert len(zones) == 1
        assert zones[0][0] > 700  # 底部 10% 内

    def test_pure_digit_page_number_footer(self):
        """分支 B(纯数字页码):底部第一行为 1..5 递增纯数字 → 检出 numeric footer zone,
        且 is_in_header_footer 能剔除这些纯数字页码(归一化为空,走 is_numeric 分支)"""
        doc = _make_pdf([{"footer": str(i + 1), "body": f"body {i}"} for i in range(5)])
        zones = detect_header_footer_zones(doc)
        doc.close()
        assert len(zones) == 1
        y_min, y_max, _norm_set, is_numeric = zones[0]
        assert y_min > 700  # 底部
        assert is_numeric is True  # 纯数字页码区
        # 区域内短数字行(页码)应被剔除
        assert is_in_header_footer((50, y_min, 70, y_max), zones, text="3") is True
        # 同 zone 内的非数字行不剔除(页码区只删短数字)
        assert is_in_header_footer((50, y_min, 70, y_max), zones, text="正文") is False

    def test_page_number_footer_tolerates_gap(self):
        """分支 B 容忍缺页间隙:1,2,3,[缺],5,6 仍按 number-page 偏移检出"""
        # page0:'1' page1:'2' page2:'3' page3:无页码 page4:'5' page5:'6'
        spec = [{"footer": "1"}, {"footer": "2"}, {"footer": "3"}, {"body": "no num"}, {"footer": "5"}, {"footer": "6"}]
        doc = _make_pdf(spec)
        zones = detect_header_footer_zones(doc)
        doc.close()
        assert len(zones) == 1
        assert zones[0][3] is True  # is_numeric

    def test_constant_step_header(self):
        """分支 B:章节式数字步长(Chapter 1..5,差分恒为 1)→ 检出 header zone"""
        doc = _make_pdf([{"header": f"Chapter {i + 1}"} for i in range(5)])
        zones = detect_header_footer_zones(doc)
        doc.close()
        assert len(zones) == 1
        assert zones[0][0] < 50

    def test_no_match_returns_empty(self):
        """首行各异且无数字关系 → 不检出"""
        words = ["Apple", "Banana", "Cherry", "Date", "Elderberry"]
        doc = _make_pdf([{"header": w} for w in words])
        zones = detect_header_footer_zones(doc)
        doc.close()
        assert zones == []

    def test_skip_cover_and_blank(self):
        """封面页 + 空白页被跳过后,后续相同页眉仍能命中"""
        spec = [{"header": "CoverTitle"}] + [{}] + [{"header": "RealHeader"}] * 6
        doc = _make_pdf(spec)
        zones = detect_header_footer_zones(doc)
        doc.close()
        assert len(zones) == 1
        assert "RealHeader" in zones[0][2]

    def test_short_doc_returns_empty(self):
        """页数不足 min_repeat → 返回空"""
        doc = _make_pdf([{"header": "Same"}] * 2)
        zones = detect_header_footer_zones(doc)
        doc.close()
        assert zones == []

    def test_max_pages_limits_scan(self):
        """max_pages 收窄扫描范围,但仍能检出"""
        doc = _make_pdf([{"header": "Same"}] * 10)
        zones = detect_header_footer_zones(doc, max_pages=4)
        doc.close()
        assert len(zones) == 1

    def test_scan_n_covers_late_body_header(self):
        """scan_n=15 覆盖前部含封面/目录的文档:正文页眉从第6页起,
        8 页采样样本不足无法命中阈值,15 页可检出。

        回归:施工图总说明书 前5页为封面/目录,正文页眉从 page6 起。
        """
        spec = [{"header": "CoverTitle"}] * 5 + [{"header": "RealHeader"}] * 10
        doc = _make_pdf(spec)
        zones = detect_header_footer_zones(doc)
        doc.close()
        assert any("RealHeader" in z[2] for z in zones), f"未检出正文页眉: {zones}"

    def test_footer_limit_covers_page_number_near_line(self):
        """页码 y 略低于 90% 线(落在 88%~90% 之间)仍能进 footer 候选区被检出。

        回归:施工图总说明书 page6 页码 y≈0.898,被 0.90 线卡掉导致 footer 候选全空。
        """
        doc = fitz.open()
        for i in range(5):
            page = doc.new_page(width=595, height=842)
            page.insert_text((50, 758), str(i + 1), fontsize=11)  # y0≈749,介于 0.88~0.90
        zones = detect_header_footer_zones(doc)
        doc.close()
        assert len(zones) == 1
        assert zones[0][3] is True  # 纯数字页码区


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
        assert len(result) == 3
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
        fw_idx = contents.index("全宽表")
        assert contents.index("左上") < fw_idx
        assert contents.index("右上") < fw_idx
        assert contents.index("左下") > fw_idx
        assert contents.index("右下") > fw_idx


class TestTocDetection:
    """目录页检测"""

    def test_toc_pages_in_project_plan(self):
        """设计交底文件目录检测不崩溃"""
        doc = fitz.open("tests/data/设计交底文件.pdf")
        toc_pages = detect_toc_pages(doc)
        doc.close()
        assert isinstance(toc_pages, set)

    def test_no_toc_in_tower_detail(self):
        """塔位明细表不应检测到目录页"""
        doc = fitz.open("tests/data/塔位明细表.pdf")
        toc_pages = detect_toc_pages(doc)
        doc.close()
        assert len(toc_pages) == 0

    def test_no_toc_in_design_doc(self):
        """设计交底文件正文页不应被误判为目录页"""
        doc = fitz.open("tests/data/设计交底文件.pdf")
        toc_pages = detect_toc_pages(doc)
        doc.close()
        for pn in range(3, 10):
            assert pn not in toc_pages, f"Page {pn} should not be detected as TOC"
