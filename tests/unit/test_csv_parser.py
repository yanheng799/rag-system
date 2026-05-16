"""CsvParser 单元测试"""

import os
import tempfile

import pytest

from src.ingestion.parsers.base import ParseError, format_rows
from src.ingestion.parsers.csv_parser import CsvParser, _detect_delimiter, _detect_has_header


@pytest.fixture
def parser():
    return CsvParser()


def _write_tmp(content: str, suffix: str = ".csv", encoding: str = "utf-8") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w", encoding=encoding) as f:
        f.write(content)
    return path


def _write_tmp_bytes(content: bytes, suffix: str = ".csv") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(content)
    return path


class TestCsvParserBasic:
    def test_simple_csv(self, parser):
        path = _write_tmp("Name,Age\nAlice,30\nBob,25")
        try:
            elems = parser.parse(path)
            assert len(elems) == 1
            assert elems[0].elem_type == "table"
            assert "Alice" in elems[0].content
            assert "Bob" in elems[0].content
            assert elems[0].page == 1
            assert elems[0].bbox == (0, 0, 0, 0)
        finally:
            os.unlink(path)

    def test_raw_structure(self, parser):
        path = _write_tmp("A,B\n1,2\n3,4")
        try:
            elems = parser.parse(path)
            raw = elems[0].raw
            assert "headers" in raw
            assert "rows" in raw
            assert raw["headers"] == ["A", "B"]
            assert len(raw["rows"]) == 2
        finally:
            os.unlink(path)

    def test_supported_types(self, parser):
        assert parser.supported_types() == ["csv"]


class TestCsvParserChunking:
    def test_chunking_at_100_rows(self, parser):
        lines = ["Col1,Col2"] + [f"val{i},data{i}" for i in range(150)]
        path = _write_tmp("\n".join(lines))
        try:
            elems = parser.parse(path)
            assert len(elems) == 2
            # 第一个 chunk 恰好 100 行
            assert len(elems[0].raw["rows"]) == 100
        finally:
            os.unlink(path)

    def test_exactly_100_rows(self, parser):
        lines = ["A,B"] + [f"{i},{i}" for i in range(100)]
        path = _write_tmp("\n".join(lines))
        try:
            elems = parser.parse(path)
            assert len(elems) == 1
            assert len(elems[0].raw["rows"]) == 100
        finally:
            os.unlink(path)


class TestCsvParserDelimiters:
    def test_comma_delimiter(self, parser):
        path = _write_tmp("A,B\n1,2")
        try:
            elems = parser.parse(path)
            assert len(elems[0].raw["headers"]) == 2
        finally:
            os.unlink(path)

    def test_semicolon_delimiter(self, parser):
        path = _write_tmp("A;B\n1;2")
        try:
            elems = parser.parse(path)
            assert len(elems[0].raw["headers"]) == 2
        finally:
            os.unlink(path)

    def test_tab_delimiter(self, parser):
        path = _write_tmp("A\tB\n1\t2")
        try:
            elems = parser.parse(path)
            assert len(elems[0].raw["headers"]) == 2
        finally:
            os.unlink(path)

    def test_explicit_delimiter(self):
        p = CsvParser(delimiter=";")
        path = _write_tmp("A;B\n1;2")
        try:
            elems = p.parse(path)
            assert len(elems[0].raw["headers"]) == 2
        finally:
            os.unlink(path)


class TestCsvParserHeader:
    def test_no_header(self, parser):
        path = _write_tmp("1,2\n3,4\n5,6")
        try:
            elems = parser.parse(path)
            raw = elems[0].raw
            assert raw["headers"] == ["列1", "列2"]
            assert len(raw["rows"]) == 3
        finally:
            os.unlink(path)


class TestCsvParserEncoding:
    def test_gbk_encoding(self):
        parser = CsvParser()
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="gbk") as f:
            f.write("名称,价格\n苹果,5元\n香蕉,3元")
        try:
            elems = parser.parse(path)
            assert "苹果" in elems[0].content
        finally:
            os.unlink(path)

    def test_utf8_bom(self):
        parser = CsvParser()
        path = _write_tmp("名称,价格\n苹果,5元", encoding="utf-8-sig")
        try:
            elems = parser.parse(path)
            assert "苹果" in elems[0].content
        finally:
            os.unlink(path)


class TestCsvParserEdgeCases:
    def test_empty_file(self, parser):
        path = _write_tmp("")
        try:
            assert parser.parse(path) == []
        finally:
            os.unlink(path)

    def test_header_only(self, parser):
        path = _write_tmp("A,B,C")
        try:
            elems = parser.parse(path)
            # 只有一行，无论是否检测为表头，raw["rows"] 都可能为空或有数据
            assert len(elems) >= 1
        finally:
            os.unlink(path)

    def test_nonexistent_file(self, parser):
        with pytest.raises(ParseError):
            parser.parse("/nonexistent/file.csv")

    def test_single_column(self, parser):
        path = _write_tmp("Value\n1\n2\n3")
        try:
            elems = parser.parse(path)
            # Sniffer 可能检测到表头，rows 可能是 3 或 2+header
            assert len(elems) >= 1
            total_data = sum(len(e.raw["rows"]) for e in elems)
            assert total_data >= 3  # 至少有 3 条数据行
        finally:
            os.unlink(path)


class TestFormatRows:
    def test_basic(self):
        result = format_rows(["A", "B"], [["1", "2"]])
        assert "表头: A | B" in result
        assert "A: 1; B: 2" in result

    def test_with_sheet_name(self):
        result = format_rows(["A"], [["1"]], sheet_name="Sheet1")
        assert "工作表: Sheet1" in result

    def test_empty_values_skipped(self):
        result = format_rows(["A", "B"], [["1", ""]])
        assert "A: 1" in result
        assert "B:" not in result

    def test_placeholder_column_name(self):
        result = format_rows(["", "B"], [["1", "2"]])
        assert "列1: 1" in result


class TestDetectDelimiter:
    def test_comma(self):
        delim, rows = _detect_delimiter("a,b\nc,d")
        assert delim == ","
        assert len(rows) == 2

    def test_tab(self):
        delim, rows = _detect_delimiter("a\tb\nc\td")
        assert delim == "\t"

    def test_with_hint(self):
        delim, rows = _detect_delimiter("a;b\nc;d", hint=";")
        assert delim == ";"


class TestDetectHasHeader:
    def test_with_header(self):
        assert _detect_has_header([["Name", "Age"], ["Alice", "30"]]) is True

    def test_no_header(self):
        assert _detect_has_header([["1", "2"], ["3", "4"], ["5", "6"]]) is False
