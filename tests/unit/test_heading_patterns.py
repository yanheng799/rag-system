"""标题正则匹配测试 — heading_patterns 模块"""

from src.ingestion.chunkers.heading_patterns import (
    is_heading_by_pattern,
    is_heading_combined,
)


class TestHeadingPatterns:
    """标题正则匹配"""

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
