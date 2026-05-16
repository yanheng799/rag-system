"""TxTParser 单元测试"""

import os
import tempfile

import pytest

from src.ingestion.parsers.base import ParseError
from src.ingestion.parsers.txt_parser import TxTParser


@pytest.fixture
def parser():
    return TxTParser()


def _write_tmp(content: str, suffix: str = ".txt", encoding: str = "utf-8") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w", encoding=encoding) as f:
        f.write(content)
    return path


class TestTxTParserBasic:
    def test_single_paragraph(self, parser):
        path = _write_tmp("Hello world")
        try:
            elems = parser.parse(path)
            assert len(elems) == 1
            assert elems[0].elem_type == "text"
            assert elems[0].content == "Hello world"
            assert elems[0].page == 1
            assert elems[0].bbox == (0, 0, 0, 0)
        finally:
            os.unlink(path)

    def test_multiple_paragraphs(self, parser):
        path = _write_tmp("Para 1\n\nPara 2\n\nPara 3")
        try:
            elems = parser.parse(path)
            assert len(elems) == 3
            assert elems[0].content == "Para 1"
            assert elems[1].content == "Para 2"
            assert elems[2].content == "Para 3"
        finally:
            os.unlink(path)

    def test_paragraph_break_marker(self, parser):
        path = _write_tmp("Line 1\n\nLine 2")
        try:
            elems = parser.parse(path)
            assert len(elems) == 2
            assert elems[0].style.get("paragraph_break") is True
            assert elems[1].style.get("paragraph_break") is True
        finally:
            os.unlink(path)

    def test_supported_types(self, parser):
        assert parser.supported_types() == ["txt"]


class TestTxTParserEdgeCases:
    def test_empty_file(self, parser):
        path = _write_tmp("")
        try:
            elems = parser.parse(path)
            assert elems == []
        finally:
            os.unlink(path)

    def test_whitespace_only_file(self, parser):
        path = _write_tmp("   \n\n  \n\n   ")
        try:
            elems = parser.parse(path)
            assert elems == []
        finally:
            os.unlink(path)

    def test_multiple_blank_lines(self, parser):
        path = _write_tmp("Para 1\n\n\n\nPara 2")
        try:
            elems = parser.parse(path)
            assert len(elems) == 2
            assert elems[0].content == "Para 1"
            assert elems[1].content == "Para 2"
        finally:
            os.unlink(path)

    def test_trailing_newlines(self, parser):
        path = _write_tmp("Content\n\n\n")
        try:
            elems = parser.parse(path)
            assert len(elems) == 1
            assert elems[0].content == "Content"
        finally:
            os.unlink(path)

    def test_single_long_paragraph(self, parser):
        content = "A" * 5000
        path = _write_tmp(content)
        try:
            elems = parser.parse(path)
            assert len(elems) == 1
            assert elems[0].content == content
        finally:
            os.unlink(path)


class TestTxTParserEncoding:
    def test_utf8_with_bom(self, parser):
        path = _write_tmp("中文内容", encoding="utf-8-sig")
        try:
            elems = parser.parse(path)
            assert len(elems) == 1
            assert elems[0].content == "中文内容"
        finally:
            os.unlink(path)

    def test_gbk_encoding(self, parser):
        fd, path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, "w", encoding="gbk") as f:
            f.write("中文GBK编码")
        try:
            elems = parser.parse(path)
            assert len(elems) == 1
            assert elems[0].content == "中文GBK编码"
        finally:
            os.unlink(path)

    def test_latin1_encoding(self, parser):
        fd, path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, "wb") as f:
            f.write(b"\xe9\xe8\xe0")  # é è à in latin-1
        try:
            elems = parser.parse(path)
            assert len(elems) == 1
        finally:
            os.unlink(path)

    def test_nonexistent_file(self, parser):
        with pytest.raises(ParseError):
            parser.parse("/nonexistent/file.txt")
