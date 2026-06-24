"""PDF 文档解析器（基于 pymupdf）"""

from __future__ import annotations

import logging
from collections import Counter

import fitz  # pymupdf

from src.ingestion.chunkers.heading_patterns import is_heading_by_pattern, is_heading_combined
from src.ingestion.chunkers.layout_detector import (
    detect_header_footer_zones,
    detect_page_layout,
    detect_toc_pages,
    is_in_header_footer,
    reorder_elements_for_layout,
)
from src.ingestion.parsers.base import BaseParser, ParsedElement, ParseError

logger = logging.getLogger(__name__)


class PDFParser(BaseParser):
    """使用 pymupdf 解析 PDF 文档，提取文字块、表格和图片"""

    def __init__(self, extract_images: bool = True):
        self._do_extract_images = extract_images

    def parse(self, file_path: str, max_pages: int | None = None) -> list[ParsedElement]:
        try:
            doc = fitz.open(file_path)
        except Exception as e:
            raise ParseError(file_path, str(e)) from e

        hf_zones = detect_header_footer_zones(doc, max_pages=max_pages)
        toc_pages = detect_toc_pages(doc)

        total_pages = len(doc)
        if max_pages is not None:
            total_pages = min(total_pages, max_pages)

        elements: list[ParsedElement] = []
        page_sizes: dict[int, tuple[float, float]] = {}
        page_layouts: dict[int, str] = {}

        for page_num in range(total_pages):
            if page_num in toc_pages:
                continue

            page = doc[page_num]
            page_sizes[page_num] = (page.rect.width, page.rect.height)
            layout = detect_page_layout(page)
            page_layouts[page_num] = layout
            elements.extend(self._parse_page(page, page_num, layout, hf_zones))

        # 提取图片（需在 doc 关闭前）
        if self._do_extract_images:
            img_elements = self._extract_images(doc, page_sizes)
            elements.extend(img_elements)

        # 图片追加在末尾，需按页码+y坐标重新排序以正确插入
        elements.sort(key=lambda e: (e.page, e.bbox[1], e.bbox[0]))

        doc.close()

        # 后处理：跨页/跨列表格合并
        from src.ingestion.chunkers.merge_cross_page import (
            merge_cross_column_tables,
            merge_cross_page_tables,
        )

        elements = merge_cross_page_tables(elements, page_sizes)
        elements = merge_cross_column_tables(elements, page_sizes)

        # 最后：按页做双栏重排（左栏 → 右栏）
        elements = self._reorder_by_layout(elements, page_sizes, page_layouts)

        logger.info("PDF 解析完成: %s, 共 %d 个元素", file_path, len(elements))
        return elements

    def _reorder_by_layout(
        self,
        elements: list[ParsedElement],
        page_sizes: dict[int, tuple[float, float]],
        page_layouts: dict[int, str],
    ) -> list[ParsedElement]:
        """按页分组，对双栏页做左栏→右栏重排"""
        page_groups: dict[int, list[ParsedElement]] = {}
        for e in elements:
            page_groups.setdefault(e.page, []).append(e)

        result: list[ParsedElement] = []
        for pn in sorted(page_groups):
            group = page_groups[pn]
            layout = page_layouts.get(pn, "single")
            pw = page_sizes.get(pn, (0, 0))[0]
            if layout == "double" and pw > 0:
                group = reorder_elements_for_layout(group, pw, layout)
            result.extend(group)

        return result

    def _parse_page(
        self,
        page: fitz.Page,
        page_num: int,
        layout: str = "single",
        hf_zones: list | None = None,
    ) -> list[ParsedElement]:
        """解析单页，提取文字和表格"""
        elements: list[ParsedElement] = []

        # 先提取表格区域，用于过滤文字块中的表格部分
        try:
            tables = page.find_tables()
        except Exception:
            logger.warning("find_tables 失败: page %d，跳过表格提取", page_num)
            tables = []
        table_bboxes = []

        for table_idx, table in enumerate(tables):
            bbox = table.bbox
            table_bboxes.append(bbox)

            # 提取表格内容
            table_text = self._extract_table_text(table)

            # 跳过无效表格：内容为空或几乎全为空单元格
            if not table_text or not self._is_valid_table(table):
                continue

            elements.append(
                ParsedElement(
                    elem_type="table",
                    content=table_text,
                    page=page_num,
                    bbox=tuple(bbox),
                    style={"table_index": table_idx},
                    raw=table,
                )
            )

        # 提取文字块（排除已识别为表格的区域和页眉页脚）
        text_elements = self._extract_text_blocks(page, page_num, table_bboxes, hf_zones)
        elements.extend(text_elements)

        # 按 y 坐标排序（从上到下），x 坐标为次要排序
        elements.sort(key=lambda e: (e.bbox[1], e.bbox[0]))

        return elements

    def _extract_text_blocks(
        self,
        page: fitz.Page,
        page_num: int,
        table_bboxes: list,
        hf_zones: list | None = None,
    ) -> list[ParsedElement]:
        """提取文字块，同一 block 内连续同类型行合并为一个段落元素"""
        elements: list[ParsedElement] = []
        page_height = page.rect.height
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

        # 统计页面字号众数，作为正文基准字号
        body_font_size = self._detect_body_font_size(blocks, page_height, hf_zones)

        for block in blocks:
            if block["type"] != 0:  # 只处理文字块
                continue

            block_bbox = block["bbox"]

            # 跳过与表格重叠的文字块
            if self._is_in_table(block_bbox, table_bboxes):
                continue

            # 阶段 1：收集有效行数据
            line_data_list: list[dict] = []
            for line in block["lines"]:
                line_bbox = tuple(line["bbox"])

                line_text = ""
                max_font_size = 0.0
                is_bold = False

                for span in line["spans"]:
                    line_text += span["text"]
                    if span["size"] > max_font_size:
                        max_font_size = span["size"]
                    if "bold" in span["font"].lower():
                        is_bold = True

                line_text = line_text.strip()
                if not line_text:
                    continue

                if hf_zones and is_in_header_footer(line_bbox, hf_zones, text=line_text):
                    continue

                # 页码不再用独立的"位置区域+短数字"启发式判断（会误杀顶部页边距里的
                # 章节编号）；页码只存在于页眉/页脚区域内，由上面的 is_in_header_footer
                # 区域整体剔除承担。

                elem_type = self._detect_text_type(line_text, max_font_size, is_bold, body_font_size)
                line_data_list.append(
                    {
                        "text": line_text,
                        "bbox": line_bbox,
                        "font_size": max_font_size,
                        "bold": is_bold,
                        "elem_type": elem_type,
                    }
                )

            # 阶段 2：按连续同类型分组，标题始终独立
            if not line_data_list:
                continue

            groups: list[list[dict]] = []
            current = [line_data_list[0]]

            for i in range(1, len(line_data_list)):
                curr = line_data_list[i]
                prev_type = current[-1]["elem_type"]

                # 标题始终独立成组
                if curr["elem_type"] == "title":
                    groups.append(current)
                    current = [curr]
                    continue

                # 上一行是标题，标题独立，当前行开始新组
                if prev_type == "title":
                    groups.append(current)
                    current = [curr]
                    continue

                # 同类型合并
                if curr["elem_type"] == prev_type:
                    current.append(curr)
                    continue

                # 类型变化，分割
                groups.append(current)
                current = [curr]

            groups.append(current)

            # 阶段 3：每组生成一个 ParsedElement
            for group in groups:
                if len(group) == 1:
                    ld = group[0]
                    elements.append(
                        ParsedElement(
                            elem_type=ld["elem_type"],
                            content=ld["text"],
                            page=page_num,
                            bbox=ld["bbox"],
                            style={"font_size": ld["font_size"], "bold": ld["bold"]},
                        )
                    )
                else:
                    elements.append(self._merge_line_group(group, page_num))

        return elements

    @staticmethod
    def _merge_line_group(group: list[dict], page_num: int) -> ParsedElement:
        """将同类型的行数据列表合并为一个 ParsedElement"""
        merged_text = " ".join(ld["text"] for ld in group)
        merged_bbox = (
            min(ld["bbox"][0] for ld in group),
            min(ld["bbox"][1] for ld in group),
            max(ld["bbox"][2] for ld in group),
            max(ld["bbox"][3] for ld in group),
        )
        max_font = max(ld["font_size"] for ld in group)
        any_bold = any(ld["bold"] for ld in group)
        elem_type = group[0]["elem_type"]

        return ParsedElement(
            elem_type=elem_type,
            content=merged_text,
            page=page_num,
            bbox=merged_bbox,
            style={"font_size": max_font, "bold": any_bold},
        )

    def _extract_table_text(self, table) -> str:
        """将 pymupdf 表格对象提取为 Markdown 表格"""
        rows = table.extract()
        if not rows:
            return ""

        md_lines = []
        for i, row in enumerate(rows):
            cells = [str(cell).replace("|", "｜").replace("\n", "<br>") if cell else "" for cell in row]
            md_lines.append("| " + " | ".join(cells) + " |")
            # 表头后插入分隔行
            if i == 0:
                md_lines.append("|" + "|".join("---" for _ in cells) + "|")

        return "\n".join(md_lines)

    @staticmethod
    def _is_valid_table(table) -> bool:
        """判断表格是否有效：超过半数行有非空单元格"""
        rows = table.extract()
        if not rows:
            return False
        non_empty_rows = sum(1 for row in rows if any(cell and str(cell).strip() for cell in row))
        return non_empty_rows > len(rows) / 2

    def _is_in_table(self, bbox, table_bboxes: list) -> bool:
        """判断文字块是否在表格区域内"""
        x0, y0, x1, y1 = bbox
        block_area = (x1 - x0) * (y1 - y0)
        return any(
            x0 < tx1
            and x1 > tx0
            and y0 < ty1
            and y1 > ty0
            and block_area > 0
            and (min(x1, tx1) - max(x0, tx0)) * (min(y1, ty1) - max(y0, ty0)) / block_area > 0.5
            for tx0, ty0, tx1, ty1 in table_bboxes
        )

    def _detect_text_type(self, text: str, font_size: float, is_bold: bool, body_font_size: float = 0.0) -> str:
        """根据样式和正则判断文字类型。

        body_font_size 为页面正文基准字号。当已知基准时，用相对阈值判断标题
        （字号 > 基准 × 1.15 且加粗，或字号 > 基准 × 1.3）；否则回退到绝对阈值。
        """
        if body_font_size > 0:
            ratio = font_size / body_font_size
            is_heading_style = ratio > 1.3 or (ratio > 1.15 and is_bold)
            # 有基准字号时，仅用正则做补充（不再用绝对字号阈值）
            is_heading = is_heading_style or is_heading_by_pattern(text)
        else:
            is_heading = is_heading_combined(text, font_size, is_bold)

        if is_heading:
            return "title"
        if text.startswith(("•", "●", "◆", "○", "■")) or (len(text) > 2 and text[0].isdigit() and text[1] in ".)"):
            return "list_item"
        return "text"

    @staticmethod
    def _detect_body_font_size(
        blocks: list[dict],
        page_height: float,
        hf_zones: list | None = None,
    ) -> float:
        """统计页面内字号众数，作为正文基准字号。"""
        size_counter: Counter[float] = Counter()
        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                line_bbox = tuple(line["bbox"])
                line_text = "".join(s["text"] for s in line["spans"]).strip()
                if hf_zones and is_in_header_footer(line_bbox, hf_zones, text=line_text):
                    continue
                for span in line["spans"]:
                    text = span["text"].strip()
                    if not text:
                        continue
                    # 排除页面边缘的页码区域
                    y0 = line_bbox[1]
                    if y0 < page_height * 0.08 or y0 > page_height * 0.90:
                        continue
                    size = round(span["size"], 1)
                    size_counter[size] += len(text)

        if not size_counter:
            return 0.0

        # 按字符数加权，取众数
        return size_counter.most_common(1)[0][0]

    def _extract_images(
        self,
        doc: fitz.Document,
        page_sizes: dict[int, tuple[float, float]],
    ) -> list[ParsedElement]:
        """提取 PDF 中内嵌的实质图片（过滤小图标和表格内图片）"""
        from src.ingestion.table_processor.image_extractor import (
            MIN_IMAGE_AREA_RATIO,
            MIN_IMAGE_DIMENSION,
        )

        elements: list[ParsedElement] = []
        img_global_index = 0

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_area = page.rect.width * page.rect.height

            # 收集该页表格 bbox 用于排除表格内图片
            try:
                tables = page.find_tables()
            except Exception:
                logger.debug("find_tables 失败(图片提取): page %d", page_num)
                tables = []
            table_bboxes = [tuple(t.bbox) for t in tables]

            image_infos = page.get_image_info(xrefs=True)
            image_list = page.get_images(full=True)

            # 建立 xref → info 映射
            xref_map: dict[int, dict] = {}
            for info in image_infos:
                xref = info.get("xref", 0)
                if xref > 0:
                    xref_map[xref] = info

            page_img_idx = 0
            seen_xrefs: set[int] = set()

            for img_ref in image_list:
                xref = img_ref[0]
                if xref == 0 or xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)

                info = xref_map.get(xref)
                if not info:
                    continue

                bbox = info.get("bbox", (0, 0, 0, 0))
                w = info.get("width", 0)
                h = info.get("height", 0)

                # 过滤小图标
                if w < MIN_IMAGE_DIMENSION or h < MIN_IMAGE_DIMENSION:
                    continue

                # 过滤面积占比过小
                bbox_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                if page_area > 0 and bbox_area / page_area < MIN_IMAGE_AREA_RATIO:
                    continue

                # 过滤与表格重叠
                overlaps = False
                for tb in table_bboxes:
                    ix0 = max(bbox[0], tb[0])
                    iy0 = max(bbox[1], tb[1])
                    ix1 = min(bbox[2], tb[2])
                    iy1 = min(bbox[3], tb[3])
                    if ix0 < ix1 and iy0 < iy1:
                        inter = (ix1 - ix0) * (iy1 - iy0)
                        if bbox_area > 0 and inter / bbox_area > 0.5:
                            overlaps = True
                            break
                if overlaps:
                    continue

                # 提取图片数据
                try:
                    img_data = doc.extract_image(xref)
                except Exception:
                    continue
                if not img_data or not img_data.get("image"):
                    continue

                ext = img_data.get("ext", "png")
                filename = f"img_p{page_num + 1}_{page_img_idx}.{ext}"

                elements.append(
                    ParsedElement(
                        elem_type="image",
                        content=f"[图片: {filename}]",
                        page=page_num,
                        bbox=tuple(bbox),
                        style={"width": w, "height": h},
                        raw={
                            "image_bytes": img_data["image"],
                            "ext": ext,
                            "filename": filename,
                        },
                    )
                )
                page_img_idx += 1
                img_global_index += 1

        logger.info("PDF 图片提取: %d 张", len(elements))
        return elements

    def supported_types(self) -> list[str]:
        return ["pdf"]
