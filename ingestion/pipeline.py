"""摄入主流程 Pipeline（同步版）"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Optional

from config.settings import settings
from ingestion.chunkers.chunk_assembler import ChunkBuilder
from ingestion.chunkers.paragraph_grouper import group_elements_by_paragraph
from ingestion.embedder import Embedder
from ingestion.parsers.registry import ParserRegistry
from ingestion.table_processor.describer import TableDescriber
from ingestion.table_processor.screenshot import TableScreenshot
from models.chunks import MixedChunk
from models.documents import ChunkRecord, DocumentRecord
from storage.ports import DocumentStorePort, ObjectStorePort, VectorStorePort

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
    ) -> None:
        """
        完整摄入流程：
        1. 更新状态为 processing
        2. 上传原始文件至 OSS
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
            filename = os.path.basename(file_path)
            with open(file_path, "rb") as f:
                file_data = f.read()
            raw_file_url = self._oss.upload_raw_doc(doc_id, filename, file_data)

            # 3. 解析文档
            parser = ParserRegistry.get(file_type)
            elements = parser.parse(file_path)
            logger.info("文档解析完成: %d 个元素", len(elements))

            if not elements:
                await self._doc_store.update_status(doc_id, "done")
                logger.info("文档无内容，跳过: doc_id=%s", doc_id)
                return

            # 4. 段落边界识别
            paragraphs = group_elements_by_paragraph(
                elements,
                vertical_gap_threshold=settings.chunk_vertical_gap,
                max_chunk_size=settings.chunk_max_size,
            )
            logger.info("段落聚合完成: %d 个段落组", len(paragraphs))

            # 5. 组装 MixedChunk
            chunks: list[MixedChunk] = []
            # 按 page 分组计数 chunk_index
            page_chunk_counters: dict[int, int] = {}

            for para_group in paragraphs:
                # 使用第一个元素的 page 作为 chunk 的 page
                page = para_group[0].page if para_group else 0
                chunk_index = page_chunk_counters.get(page, 0)
                page_chunk_counters[page] = chunk_index + 1

                pdf_path = file_path if file_type == "pdf" else None
                chunk = self._chunk_builder.build(
                    elements=para_group,
                    doc_id=doc_id,
                    source=filename,
                    page=page,
                    chunk_index=chunk_index,
                    pdf_path=pdf_path,
                )
                chunks.append(chunk)

            logger.info("MixedChunk 组装完成: %d 个分块", len(chunks))

            # 6. Embedding 向量化（过滤空文本）
            non_empty_chunks = [c for c in chunks if c.full_text.strip()]
            if not non_empty_chunks:
                await self._doc_store.update_status(doc_id, "done")
                logger.info("文档所有分块为空，跳过: doc_id=%s", doc_id)
                return
            texts = [c.full_text for c in non_empty_chunks]
            embeddings = self._embedder.embed(texts)

            # 7. 写入 Milvus
            milvus_records = []
            for chunk, embedding in zip(non_empty_chunks, embeddings):
                milvus_records.append({
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
                })
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
                )
                await self._doc_store.save_chunk(chunk_record)

            # 9. 更新状态为 done
            await self._doc_store.update_status(doc_id, "done")
            logger.info("文档摄入成功: doc_id=%s, 共 %d 个分块", doc_id, len(non_empty_chunks))

        except Exception as e:
            logger.error("文档摄入失败: doc_id=%s, 错误: %s", doc_id, str(e))
            await self._doc_store.update_status(doc_id, "failed", error_msg=str(e))
            raise


def generate_doc_id() -> str:
    """生成文档唯一 ID"""
    return f"doc_{uuid.uuid4().hex[:12]}"
