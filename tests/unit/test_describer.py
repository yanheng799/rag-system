"""表格语义描述生成模块测试"""

from src.ingestion.parsers.base import ParsedElement
from src.ingestion.table_processor.describer import TableDescriber


class TestTableDescriber:
    """表格规则描述测试"""

    def setup_method(self):
        self.describer = TableDescriber()

    def test_pipe_separated_format(self):
        """PDF/Word Parser 输出的 | 分隔格式"""
        elem = ParsedElement(
            elem_type="table",
            content="区域 | 目标 | 实际\n华东 | 111万 | 120万\n华南 | 95万 | 98万",
            page=0,
        )
        result = self.describer.describe(elem)
        assert "区域" in result
        assert "目标" in result
        assert "华东" in result
        assert "120万" in result

    def test_excel_format(self):
        """Excel Parser 直接产生的格式"""
        elem = ParsedElement(
            elem_type="table",
            content="工作表: Sheet1\n表头: 序号 | 名称\n序号: 1; 名称: 塔型A",
            page=1,
        )
        result = self.describer.describe(elem)
        assert "工作表" in result

    def test_empty_content(self):
        """空内容"""
        elem = ParsedElement(elem_type="table", content="", page=0)
        result = self.describer.describe(elem)
        assert result == ""

    def test_single_row(self):
        """只有表头"""
        elem = ParsedElement(
            elem_type="table",
            content="区域 | 目标 | 实际",
            page=0,
        )
        result = self.describer.describe(elem)
        assert "区域" in result
