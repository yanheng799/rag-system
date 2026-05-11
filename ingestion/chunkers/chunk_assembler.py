"""MixedChunk 组装器：将段落组组装为 MixedChunk"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from ingestion.chunkers.paragraph_grouper import detect_chunk_type
from ingestion.parsers.base import ParsedElement
from ingestion.table_processor.describer import TableDescriber
from ingestion.table_processor.screenshot import TableScreenshot
from models.chunks import ChunkMetadata, ContentElement, MixedChunk

logger = logging.getLogger(__name__)


class ChunkBuilder:
    """将段落组（Element 列表）组装为 MixedChunk"""

    def __init__(
        self,
        screenshot: Optional[TableScreenshot] = None,
        describer: Optional[TableDescriber] = None,
    ):
        self._screenshot = screenshot
        self._describer = describer or TableDescriber()

    def build(
        self,
        elements: list[ParsedElement],
        doc_id: str,
        source: str,
        page: int,
        chunk_index: int,
        pdf_path: Optional[str] = None,
    ) -> MixedChunk:
        """
        将段落组组装为 MixedChunk。

        遍历 elements：
        - 文字元素：直接取 content，image_url=None
        - 表格元素：生成语义描述，如有截图服务则截图
        - 图片元素：使用已上传的 OSS 路径，content 为占位文本
        """
        chunk_type = detect_chunk_type(elements)
        content_elements: list[ContentElement] = []
        image_urls: list[str] = []
        text_parts: list[str] = []
        table_counter = 0

        for elem in elements:
            if elem.is_table:
                # 表格元素
                description = self._describer.describe(elem)
                img_url = None

                # 尝试截图（需要 PDF 文件路径和截图服务）
                if (
                    self._screenshot
                    and pdf_path
                    and elem.bbox != (0, 0, 0, 0)
                ):
                    try:
                        img_url = self._screenshot.capture_pdf_table(
                            pdf_path=pdf_path,
                            page_num=elem.page,
                            bbox=elem.bbox,
                            doc_id=doc_id,
                            table_index=table_counter,
                        )
                        image_urls.append(img_url)
                    except Exception as e:
                        logger.warning("表格截图失败: %s", e)

                    # 跨页合并表格：为每个被合并的续页各截一张
                    if elem.raw and isinstance(elem.raw, dict):
                        for mp in elem.raw.get("_merged_pages", []):
                            try:
                                mp_url = self._screenshot.capture_pdf_table(
                                    pdf_path=pdf_path,
                                    page_num=mp["page"],
                                    bbox=tuple(mp["bbox"]),
                                    doc_id=doc_id,
                                    table_index=table_counter,
                                )
                                image_urls.append(mp_url)
                            except Exception as e:
                                logger.warning(
                                    "续页表格截图失败: page %d, %s",
                                    mp["page"], e,
                                )

                content_elements.append(
                    ContentElement(
                        type="table",
                        content=description,
                        image_url=img_url,
                    )
                )
                text_parts.append(description)
                table_counter += 1
            elif elem.is_image:
                # 图片元素：raw 中已有 oss_path
                img_url = None
                if elem.raw and isinstance(elem.raw, dict):
                    img_url = elem.raw.get("oss_path")
                if img_url:
                    image_urls.append(img_url)
                content_elements.append(
                    ContentElement(
                        type="image",
                        content=elem.content,
                        image_url=img_url,
                    )
                )
                text_parts.append(elem.content)
            else:
                # 文字元素
                content_elements.append(
                    ContentElement(
                        type="text",
                        content=elem.content,
                        image_url=None,
                    )
                )
                text_parts.append(elem.content)

        full_text = "\n".join(text_parts)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        all_pages = sorted(set(e.page for e in elements))
        metadata = ChunkMetadata(
            chunk_id=f"{doc_id}_p{page}_c{chunk_index}",
            chunk_type=chunk_type,
            source=source,
            page=page,
            chunk_index=chunk_index,
            char_count=len(full_text),
            created_at=now,
            doc_id=doc_id,
            pages=all_pages,
        )

        return MixedChunk(
            metadata=metadata,
            elements=content_elements,
            full_text=full_text,
            image_urls=image_urls,
        )
