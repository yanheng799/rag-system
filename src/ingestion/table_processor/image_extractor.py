"""文档图片提取模块：从 PDF/Word 中提取内嵌图片并上传至 MinIO"""

from __future__ import annotations

import logging
from typing import Optional

from src.storage.ports import ObjectStorePort

logger = logging.getLogger(__name__)

# 图片面积占页面面积的最小比例，低于此值忽略（过滤小图标）
MIN_IMAGE_AREA_RATIO = 0.005
# 图片最小宽高像素，低于此值忽略（过滤装饰线）
MIN_IMAGE_DIMENSION = 50


class ImageExtractor:
    """文档图片提取器"""

    def __init__(self, oss: ObjectStorePort):
        self._oss = oss

    def extract_pdf_images(
        self,
        pdf_path: str,
        doc_id: str,
        table_bboxes: Optional[dict] = None,
    ) -> list:
        """
        从 PDF 中提取内嵌图片。

        Args:
            pdf_path: PDF 文件路径
            doc_id: 文档 ID
            table_bboxes: 每页的表格 bbox 列表，{page_num: [(x0, y0, x1, y1), ...]}
        """
        import fitz

        from src.ingestion.parsers.base import ParsedElement

        if table_bboxes is None:
            table_bboxes = {}

        doc = fitz.open(pdf_path)
        elements: list[ParsedElement] = []

        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_rect = page.rect
                page_area = page_rect.width * page_rect.height

                # 获取页面图片信息（含 bbox 和 xref）
                image_infos = page.get_image_info(xrefs=True)
                # 获取图片引用列表
                image_list = page.get_images(full=True)

                # 建立 xref → image_info 映射
                xref_to_info: dict[int, dict] = {}
                for info in image_infos:
                    xref = info.get("xref", 0)
                    if xref > 0:
                        xref_to_info[xref] = info

                page_img_index = 0
                for img_ref in image_list:
                    xref = img_ref[0]
                    if xref == 0:
                        continue

                    # 获取图片 bbox
                    info = xref_to_info.get(xref)
                    if not info:
                        continue

                    bbox = info.get("bbox", (0, 0, 0, 0))
                    img_width = info.get("width", 0)
                    img_height = info.get("height", 0)

                    # 过滤：尺寸过小
                    if img_width < MIN_IMAGE_DIMENSION or img_height < MIN_IMAGE_DIMENSION:
                        continue

                    # 过滤：面积占比过小
                    bbox_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                    if page_area > 0 and bbox_area / page_area < MIN_IMAGE_AREA_RATIO:
                        continue

                    # 过滤：与表格 bbox 重叠超过 50%
                    page_tables = table_bboxes.get(page_num, [])
                    if self._overlaps_table(bbox, page_tables):
                        continue

                    # 提取图片数据
                    try:
                        img_data = doc.extract_image(xref)
                    except Exception:
                        logger.warning("图片提取失败: xref=%d, page=%d", xref, page_num)
                        continue

                    if not img_data or not img_data.get("image"):
                        continue

                    ext = img_data.get("ext", "png")
                    image_bytes = img_data["image"]
                    filename = f"{doc_id}_p{page_num + 1}_img{page_img_index}.{ext}"

                    # 上传至 MinIO
                    oss_path = self._oss.upload_doc_image(
                        doc_id=doc_id,
                        page=page_num + 1,
                        image_index=page_img_index,
                        image=image_bytes,
                        ext=ext,
                    )

                    elements.append(
                        ParsedElement(
                            elem_type="image",
                            content=f"[图片: {filename}]",
                            page=page_num + 1,
                            bbox=bbox,
                            style={"width": img_width, "height": img_height},
                            raw={
                                "image_bytes": image_bytes,
                                "ext": ext,
                                "filename": filename,
                                "oss_path": oss_path,
                            },
                        )
                    )
                    page_img_index += 1

        finally:
            doc.close()

        logger.info(
            "PDF 图片提取完成: %s, 共 %d 张",
            pdf_path,
            len(elements),
        )
        return elements

    def extract_word_images(
        self,
        docx_path: str,
        doc_id: str,
    ) -> list:
        """从 Word 文档中提取内嵌图片。"""
        from docx import Document
        from docx.opc.constants import RELATIONSHIP_TYPE as RT

        from src.ingestion.parsers.base import ParsedElement

        doc = Document(docx_path)
        elements: list[ParsedElement] = []

        # 建立关系 ID → 图片 blob 映射
        image_parts = {}
        for rel in doc.part.rels.values():
            if "image" in rel.reltype:
                try:
                    blob = rel.target_part.blob
                    content_type = rel.target_part.content_type
                    ext = self._content_type_to_ext(content_type)
                    image_parts[rel.rId] = {"blob": blob, "ext": ext}
                except Exception:
                    continue

        if not image_parts:
            return elements

        img_index = 0
        for para_idx, para in enumerate(doc.paragraphs):
            # 检测段落中的 drawing 元素
            drawings = para._element.findall(
                ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing"
            )
            if not drawings:
                continue

            for drawing in drawings:
                blips = drawing.findall(
                    ".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
                )
                for blip in blips:
                    embed_attr = blip.get(
                        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
                    )
                    if not embed_attr or embed_attr not in image_parts:
                        continue

                    img_info = image_parts[embed_attr]
                    filename = f"{doc_id}_p1_img{img_index}.{img_info['ext']}"

                    oss_path = self._oss.upload_doc_image(
                        doc_id=doc_id,
                        page=1,
                        image_index=img_index,
                        image=img_info["blob"],
                        ext=img_info["ext"],
                    )

                    elements.append(
                        ParsedElement(
                            elem_type="image",
                            content=f"[图片: {filename}]",
                            page=1,
                            bbox=(0, 0, 0, 0),
                            style={"para_index": para_idx},
                            raw={
                                "ext": img_info["ext"],
                                "filename": filename,
                                "oss_path": oss_path,
                            },
                        )
                    )
                    img_index += 1

        logger.info(
            "Word 图片提取完成: %s, 共 %d 张",
            docx_path,
            len(elements),
        )
        return elements

    @staticmethod
    def _overlaps_table(
        bbox: tuple, table_bboxes: list[tuple], threshold: float = 0.5
    ) -> bool:
        """检查图片 bbox 是否与表格 bbox 重叠超过阈值。"""
        for tb in table_bboxes:
            ix0 = max(bbox[0], tb[0])
            iy0 = max(bbox[1], tb[1])
            ix1 = min(bbox[2], tb[2])
            iy1 = min(bbox[3], tb[3])

            if ix0 >= ix1 or iy0 >= iy1:
                continue

            inter_area = (ix1 - ix0) * (iy1 - iy0)
            bbox_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            if bbox_area > 0 and inter_area / bbox_area > threshold:
                return True
        return False

    @staticmethod
    def _content_type_to_ext(content_type: str) -> str:
        """将 MIME 类型转为文件扩展名。"""
        mapping = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/gif": "gif",
            "image/bmp": "bmp",
            "image/tiff": "tiff",
            "image/x-emf": "emf",
            "image/x-wmf": "wmf",
        }
        return mapping.get(content_type, "png")
