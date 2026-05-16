"""MarkdownParser 单元测试"""

import os
import tempfile

import pytest

from src.ingestion.parsers.markdown_parser import MarkdownParser, _strip_inline_formatting


@pytest.fixture
def parser():
    return MarkdownParser()


def _write_tmp(content: str, suffix: str = ".md") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class TestMarkdownParserHeadings:
    def test_h1(self, parser):
        path = _write_tmp("# Title")
        try:
            elems = parser.parse(path)
            assert len(elems) == 1
            assert elems[0].elem_type == "title"
            assert elems[0].content == "Title"
            assert elems[0].style["heading_level"] == 1
        finally:
            os.unlink(path)

    def test_multiple_heading_levels(self, parser):
        path = _write_tmp("# H1\n## H2\n### H3\n#### H4")
        try:
            elems = parser.parse(path)
            assert len(elems) == 4
            for i, level in enumerate([1, 2, 3, 4], 0):
                assert elems[i].elem_type == "title"
                assert elems[i].style["heading_level"] == level
        finally:
            os.unlink(path)


class TestMarkdownParserCodeBlocks:
    def test_fenced_code_block(self, parser):
        path = _write_tmp("```\nline 1\nline 2\n```")
        try:
            elems = parser.parse(path)
            assert len(elems) == 1
            assert elems[0].elem_type == "text"
            assert elems[0].style.get("code_block") is True
            assert "line 1" in elems[0].content
            assert "line 2" in elems[0].content
        finally:
            os.unlink(path)

    def test_code_block_with_blank_lines(self, parser):
        path = _write_tmp("```\nline 1\n\nline 2\n```")
        try:
            elems = parser.parse(path)
            assert len(elems) == 1
            assert "line 1\n\nline 2" in elems[0].content
        finally:
            os.unlink(path)

    def test_code_block_not_parsed_as_markdown(self, parser):
        path = _write_tmp("```\n# Not a heading\n- Not a list\n```")
        try:
            elems = parser.parse(path)
            assert len(elems) == 1
            assert elems[0].content == "# Not a heading\n- Not a list"
        finally:
            os.unlink(path)

    def test_tilde_fenced_code(self, parser):
        path = _write_tmp("~~~\ncode\n~~~")
        try:
            elems = parser.parse(path)
            assert len(elems) == 1
            assert elems[0].content == "code"
        finally:
            os.unlink(path)

    def test_unclosed_code_block(self, parser):
        path = _write_tmp("```\ncode line")
        try:
            elems = parser.parse(path)
            assert len(elems) == 1
            assert elems[0].content == "code line"
        finally:
            os.unlink(path)


class TestMarkdownParserLists:
    def test_unordered_list(self, parser):
        path = _write_tmp("- item 1\n- item 2\n- item 3")
        try:
            elems = parser.parse(path)
            assert len(elems) == 3
            for e in elems:
                assert e.elem_type == "list_item"
            assert elems[0].content == "item 1"
        finally:
            os.unlink(path)

    def test_ordered_list(self, parser):
        path = _write_tmp("1. first\n2. second")
        try:
            elems = parser.parse(path)
            assert len(elems) == 2
            assert elems[0].content == "first"
        finally:
            os.unlink(path)

    def test_star_list(self, parser):
        path = _write_tmp("* item a\n* item b")
        try:
            elems = parser.parse(path)
            assert len(elems) == 2
            assert elems[0].content == "item a"
        finally:
            os.unlink(path)


class TestMarkdownParserTables:
    def test_simple_table(self, parser):
        md = "| Name | Age |\n|------|-----|\n| Alice | 30 |\n| Bob | 25 |"
        path = _write_tmp(md)
        try:
            elems = parser.parse(path)
            tables = [e for e in elems if e.elem_type == "table"]
            assert len(tables) == 1
            assert "Alice" in tables[0].content
            assert "Bob" in tables[0].content
            # 分隔行不应出现在 content 中
            assert "---" not in tables[0].content
        finally:
            os.unlink(path)


class TestMarkdownParserText:
    def test_plain_text(self, parser):
        path = _write_tmp("Hello world")
        try:
            elems = parser.parse(path)
            assert len(elems) == 1
            assert elems[0].elem_type == "text"
            assert elems[0].content == "Hello world"
        finally:
            os.unlink(path)

    def test_multiline_text_paragraph(self, parser):
        path = _write_tmp("Line 1\nLine 2\nLine 3")
        try:
            elems = parser.parse(path)
            assert len(elems) == 1
            assert elems[0].content == "Line 1\nLine 2\nLine 3"
        finally:
            os.unlink(path)


class TestMarkdownParserMixed:
    def test_heading_with_paragraph(self, parser):
        path = _write_tmp("# Title\n\nParagraph text")
        try:
            elems = parser.parse(path)
            assert len(elems) == 2
            assert elems[0].elem_type == "title"
            assert elems[1].elem_type == "text"
            assert elems[1].content == "Paragraph text"
        finally:
            os.unlink(path)

    def test_complete_document(self, parser):
        md = """# Main Title

Intro paragraph.

## Section 1

- item 1
- item 2

| A | B |
|---|---|
| 1 | 2 |

```python
print("hello")
```

Outro text."""
        path = _write_tmp(md)
        try:
            elems = parser.parse(path)
            types = [e.elem_type for e in elems]
            assert "title" in types
            assert "text" in types
            assert "list_item" in types
            assert "table" in types
            # 代码块应该是 text 类型
            code_elems = [e for e in elems if e.style.get("code_block")]
            assert len(code_elems) == 1
        finally:
            os.unlink(path)


class TestInlineFormatting:
    def test_bold_stripped(self):
        assert _strip_inline_formatting("**bold**") == "bold"

    def test_italic_stripped(self):
        assert _strip_inline_formatting("*italic*") == "italic"

    def test_link_stripped(self):
        assert _strip_inline_formatting("[text](http://example.com)") == "text"

    def test_image_to_alt(self):
        assert _strip_inline_formatting("![alt text](img.png)") == "alt text"

    def test_image_no_alt(self):
        assert _strip_inline_formatting("![](img.png)") == "[图片]"

    def test_code_preserved(self):
        assert "`code`" in _strip_inline_formatting("use `code` here")


class TestMarkdownParserEdgeCases:
    def test_empty_file(self, parser):
        path = _write_tmp("")
        try:
            assert parser.parse(path) == []
        finally:
            os.unlink(path)

    def test_supported_types(self, parser):
        assert parser.supported_types() == ["md"]

    def test_all_elements_page1(self, parser):
        path = _write_tmp("# Title\n\nText\n\n- list\n\n```\ncode\n```")
        try:
            elems = parser.parse(path)
            for e in elems:
                assert e.page == 1
                assert e.bbox == (0, 0, 0, 0)
        finally:
            os.unlink(path)
