"""表格截图模块：将文档中的表格区域渲染为截图"""

from __future__ import annotations

import io
import logging
import os
import subprocess
import tempfile

import fitz  # pymupdf
from PIL import Image

from src.storage.ports import ObjectStorePort

logger = logging.getLogger(__name__)

# 截图边距（像素）
SCREENSHOT_PADDING = 5
# 默认 DPI
DEFAULT_DPI = 150


class TableScreenshot:
    """表格截图处理：支持 PDF 和 Word 文档"""

    def __init__(self, oss_store: ObjectStorePort):
        self._oss = oss_store

    def capture_pdf_table(
        self,
        pdf_path: str,
        page_num: int,
        bbox: tuple,
        doc_id: str,
        table_index: int,
        dpi: int = DEFAULT_DPI,
    ) -> str:
        """
        截取 PDF 中的表格区域并上传到 OSS。

        返回 OSS 内部路径。
        """
        doc = fitz.open(pdf_path)
        page = doc[page_num]

        # 渲染页面为图片
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)

        # 转换为 PIL Image 并裁剪
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # bbox 是基于原始坐标的，需要按 DPI 缩放
        scale = dpi / 72
        x0 = max(0, int(bbox[0] * scale - SCREENSHOT_PADDING))
        y0 = max(0, int(bbox[1] * scale - SCREENSHOT_PADDING))
        x1 = min(img.width, int(bbox[2] * scale + SCREENSHOT_PADDING))
        y1 = min(img.height, int(bbox[3] * scale + SCREENSHOT_PADDING))

        cropped = img.crop((x0, y0, x1, y1))
        doc.close()

        # 转为 bytes
        buf = io.BytesIO()
        cropped.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        # 上传到 OSS
        oss_path = self._oss.upload_table_image(
            doc_id=doc_id,
            page=page_num,
            table_index=table_index,
            image=image_bytes,
        )
        logger.info("PDF 表格截图完成: %s_p%d_t%d", doc_id, page_num, table_index)
        return oss_path

    def capture_word_table(
        self,
        docx_path: str,
        doc_id: str,
        page: int,
        table_index: int,
    ) -> str | None:
        """
        截取 Word 文档中的表格。

        通过 LibreOffice 将 docx 转 PDF，再用 pymupdf 渲染整页截图。
        如果 LibreOffice 不可用，返回 None。
        """
        pdf_path = self._convert_docx_to_pdf(docx_path)
        if pdf_path is None:
            logger.warning("Word 转 PDF 失败，跳过表格截图: %s", docx_path)
            return None

        try:
            doc = fitz.open(pdf_path)
            # Word 文档无精确页码对应，渲染包含该表格的页
            # 策略：逐页查找，截取整页作为表格截图（Word 表格位置无法精确定位）
            page_num = min(page - 1, len(doc) - 1) if page > 0 else 0
            page_obj = doc[page_num]

            mat = fitz.Matrix(DEFAULT_DPI / 72, DEFAULT_DPI / 72)
            pix = page_obj.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            doc.close()

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            image_bytes = buf.getvalue()

            oss_path = self._oss.upload_table_image(
                doc_id=doc_id,
                page=page_num,
                table_index=table_index,
                image=image_bytes,
            )
            logger.info("Word 表格截图完成: %s_p%d_t%d", doc_id, page_num, table_index)
            return oss_path
        finally:
            # 清理临时 PDF
            if os.path.exists(pdf_path):
                os.remove(pdf_path)

    def _convert_docx_to_pdf(self, docx_path: str) -> str | None:
        """使用 LibreOffice 将 docx 转换为 PDF"""
        output_dir = tempfile.mkdtemp()
        try:
            result = subprocess.run(
                [
                    "soffice", "--headless", "--convert-to", "pdf",
                    "--outdir", output_dir, docx_path,
                ],
                capture_output=True,
                timeout=60,
            )
            if result.returncode != 0:
                return None

            base_name = os.path.splitext(os.path.basename(docx_path))[0]
            pdf_path = os.path.join(output_dir, f"{base_name}.pdf")
            if os.path.exists(pdf_path):
                return pdf_path
            return None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.info("LibreOffice 不可用，Word 表格截图跳过")
            return None
