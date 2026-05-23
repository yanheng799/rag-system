"""摄入主流程 Pipeline"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid

from src.config.settings import settings
from src.ingestion.chunkers.chunk_assembler import ChunkBuilder
from src.ingestion.chunkers.registry import ChunkerRegistry
from src.ingestion.embedder import Embedder
from src.ingestion.parsers.registry import ParserRegistry
from src.ingestion.table_processor.describer import TableDescriber
from src.ingestion.table_processor.screenshot import TableScreenshot
from src.models.chunks import MixedChunk
from src.models.documents import ChunkRecord
from src.storage.ports import DocumentStorePort, ObjectStorePort, VectorStorePort

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """摄入主流程：解析 → 段落聚合 → 分块 → Embedding → 写库"""

    def __init__(
        self,
        vector_store: VectorStorePort,
        doc_store: DocumentStorePort,
        oss_store: ObjectStorePort,
        embedder: Embedder,
    ):
        self._vector_store = vector_store
        self._doc_store = doc_store
        self._oss = oss_store
        self._embedder = embedder
        self._screenshot = TableScreenshot(oss_store)
        self._describer = TableDescriber()
        self._chunk_builder = ChunkBuilder(
            screenshot=self._screenshot,
            describer=self._describer,
        )

    async def ingest(
        self,
        doc_id: str,
        file_path: str,
        file_type: str,
        skip_oss_upload: bool = False,
        chunk_options=None,
        original_filename: str | None = None,
        org_id: str | None = None,
    ) -> None:
        """
        完整摄入流程：
        1. 更新状态为 processing
        2. 上传原始文件至 OSS（skip_oss_upload=True 时跳过）
        3. 解析文档
        4. 段落边界识别
        5. 组装 MixedChunk
        6. Embedding 向量化
        7. 写入 Milvus + PostgreSQL
        8. 更新状态为 done
        """
        try:
            # 1. 更新状态
            await self._doc_store.update_status(doc_id, "processing")
            logger.info("开始摄入文档: doc_id=%s, file=%s", doc_id, file_path)

            # 2. 上传原始文件至 OSS
            filename = original_filename or os.path.basename(file_path)
            if not skip_oss_upload:
                with open(file_path, "rb") as f:
                    file_data = f.read()
                self._oss.upload_raw_doc(doc_id, filename, file_data, org_id=org_id or "")

            # 3. 解析文档
            parser = ParserRegistry.get(file_type)
            elements = await asyncio.to_thread(parser.parse, file_path)
            logger.info("文档解析完成: %d 个元素", len(elements))

            if not elements:
                await self._doc_store.update_status(doc_id, "done")
                logger.info("文档无内容，跳过: doc_id=%s", doc_id)
                return

            # 4. 分块
            page_sizes: dict[int, tuple[float, float]] = {}
            if file_type == "pdf":
                page_sizes = await asyncio.to_thread(_get_pdf_page_sizes, file_path)

            strategy = "paragraph"
            max_size = settings.chunk_max_size
            min_size = 50
            overlap = 0
            vertical_gap = settings.chunk_vertical_gap

            if chunk_options:
                from src.api.schemas.documents import ChunkOptions
                if isinstance(chunk_options, dict):
                    chunk_options = ChunkOptions(**chunk_options)
                if chunk_options.strategy:
                    strategy = chunk_options.strategy
                if chunk_options.max_size is not None:
                    max_size = chunk_options.max_size
                if chunk_options.min_size is not None:
                    min_size = chunk_options.min_size
                if chunk_options.overlap is not None:
                    overlap = chunk_options.overlap
                if chunk_options.vertical_gap is not None:
                    vertical_gap = chunk_options.vertical_gap

            chunker = ChunkerRegistry.get(strategy)
            paragraphs = await asyncio.to_thread(
                chunker.chunk,
                elements,
                page_sizes,
                doc_id,
                max_size,
                min_chunk_size=min_size,
                overlap=overlap,
                vertical_gap=vertical_gap,
            )
            logger.info("分块完成: %d 个分块 (策略=%s)", len(paragraphs), strategy)

            # 5. 组装 MixedChunk
            chunks: list[MixedChunk] = []
            # 按 page 分组计数 chunk_index
            page_chunk_counters: dict[int, int] = {}
            # 按 page 计数图片索引，避免不同段落组的同名图片互相覆盖
            page_img_counters: dict[int, int] = {}

            for para_group, group_id in paragraphs:
                # 使用第一个元素的 page 作为 chunk 的 page
                page = para_group[0].page if para_group else 0
                chunk_index = page_chunk_counters.get(page, 0)
                page_chunk_counters[page] = chunk_index + 1

                # 上传图片元素至 MinIO（parser 只提取了 bytes，上传在此完成）
                img_counter = page_img_counters.get(page, 0)
                for elem in para_group:
                    if (
                        elem.is_image
                        and elem.raw
                        and isinstance(elem.raw, dict)
                        and "oss_path" not in elem.raw
                        and "image_bytes" in elem.raw
                    ):
                        ext = elem.raw.get("ext", "png")
                        oss_path = self._oss.upload_doc_image(
                            doc_id=doc_id,
                            page=page,
                            image_index=img_counter,
                            image=elem.raw["image_bytes"],
                            ext=ext,
                            org_id=org_id or "",
                        )
                        elem.raw["oss_path"] = oss_path
                        img_counter += 1
                page_img_counters[page] = img_counter

                pdf_path = file_path if file_type == "pdf" else None
                chunk = self._chunk_builder.build(
                    elements=para_group,
                    doc_id=doc_id,
                    source=filename,
                    page=page,
                    chunk_index=chunk_index,
                    pdf_path=pdf_path,
                    org_id=org_id or "",
                )
                chunk.metadata.group_id = group_id
                chunks.append(chunk)

            logger.info("MixedChunk 组装完成: %d 个分块", len(chunks))

            # 6. Embedding 向量化（过滤空文本）
            non_empty_chunks = [c for c in chunks if c.full_text.strip()]
            if not non_empty_chunks:
                await self._doc_store.update_status(doc_id, "done")
                logger.info("文档所有分块为空，跳过: doc_id=%s", doc_id)
                return
            texts = [c.full_text for c in non_empty_chunks]
            embeddings = await asyncio.to_thread(self._embedder.embed_for_index, texts)

            # 7. 写入 Milvus
            milvus_records = []
            for chunk, embedding in zip(non_empty_chunks, embeddings, strict=False):
                milvus_records.append(
                    {
                        "embedding": embedding,
                        "chunk_id": chunk.metadata.chunk_id,
                        "doc_id": chunk.metadata.doc_id,
                        "full_text": chunk.full_text,
                        "chunk_type": chunk.metadata.chunk_type,
                        "elements": [e.to_dict() for e in chunk.elements],
                        "image_urls": chunk.image_urls,
                        "source": chunk.metadata.source,
                        "page": chunk.metadata.page,
                        "chunk_index": chunk.metadata.chunk_index,
                        "char_count": chunk.metadata.char_count,
                        "created_at": chunk.metadata.created_at,
                        "pages": chunk.metadata.pages,
                        "group_id": chunk.metadata.group_id,
                        "org_id": org_id or "",
                    }
                )
            self._vector_store.insert(milvus_records)
            logger.info("Milvus 写入完成: %d 条向量记录", len(milvus_records))

            # 8. 写入 PostgreSQL chunks 表
            for chunk in non_empty_chunks:
                chunk_record = ChunkRecord(
                    chunk_id=chunk.metadata.chunk_id,
                    doc_id=chunk.metadata.doc_id,
                    chunk_type=chunk.metadata.chunk_type,
                    full_text=chunk.full_text,
                    elements=[e.to_dict() for e in chunk.elements],
                    image_urls=chunk.image_urls,
                    page=chunk.metadata.page,
                    chunk_index=chunk.metadata.chunk_index,
                    char_count=chunk.metadata.char_count,
                    group_id=chunk.metadata.group_id,
                )
                await self._doc_store.save_chunk(chunk_record)

            # 9. 更新状态为 done
            await self._doc_store.update_status(doc_id, "done")
            logger.info("文档摄入成功: doc_id=%s, 共 %d 个分块", doc_id, len(non_empty_chunks))

        except Exception as e:
            logger.error("文档摄入失败: doc_id=%s, 错误: %s", doc_id, str(e))
            await self._doc_store.update_status(doc_id, "failed", error_msg=str(e))
            raise


def _get_pdf_page_sizes(file_path: str) -> dict[int, tuple[float, float]]:
    """读取 PDF 每页尺寸"""
    import fitz

    sizes: dict[int, tuple[float, float]] = {}
    pdf_doc = fitz.open(file_path)
    for pn in range(len(pdf_doc)):
        sizes[pn] = (pdf_doc[pn].rect.width, pdf_doc[pn].rect.height)
    pdf_doc.close()
    return sizes


def generate_doc_id() -> str:
    """生成文档唯一 ID"""
    return f"doc_{uuid.uuid4().hex[:12]}"
