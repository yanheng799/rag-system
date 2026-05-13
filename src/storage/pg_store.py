"""PostgreSQL 文档/分块存储实现"""

from __future__ import annotations

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config.settings import settings
from src.models.documents import ChunkRecord, DatasetRecord, DocumentRecord, QueryLogRecord
from src.storage.pg_models import ChunkORM, DatasetORM, DocumentORM, QueryLogORM
from src.storage.ports import DocumentStorePort


class PgStore(DocumentStorePort):
    """PostgreSQL 文档存储实现"""

    def __init__(self, dsn: str | None = None):
        dsn = dsn or settings.postgres_dsn
        self._engine = create_async_engine(dsn, echo=False, pool_size=10, max_overflow=20)
        self._session_factory = async_sessionmaker(self._engine, class_=AsyncSession, expire_on_commit=False)

    async def get_session(self) -> AsyncSession:
        return self._session_factory()

    async def save_document(self, doc: DocumentRecord) -> None:
        async with self._session_factory() as session:
            orm = DocumentORM(
                doc_id=doc.doc_id,
                dataset_id=doc.dataset_id,
                content_hash=doc.content_hash,
                filename=doc.filename,
                raw_file_url=doc.raw_file_url,
                file_size=doc.file_size,
                file_type=doc.file_type,
                status=doc.status,
                created_by=doc.created_by,
            )
            session.add(orm)
            await session.commit()

    async def update_status(self, doc_id: str, status: str, error_msg: str | None = None) -> None:
        async with self._session_factory() as session:
            stmt = update(DocumentORM).where(DocumentORM.doc_id == doc_id).values(status=status, error_msg=error_msg)
            await session.execute(stmt)
            await session.commit()

    async def get_document(self, doc_id: str) -> DocumentRecord | None:
        async with self._session_factory() as session:
            result = await session.execute(select(DocumentORM).where(DocumentORM.doc_id == doc_id))
            orm = result.scalar_one_or_none()
            if orm is None:
                return None
            return DocumentRecord(
                doc_id=orm.doc_id,
                dataset_id=orm.dataset_id,
                content_hash=orm.content_hash,
                filename=orm.filename,
                raw_file_url=orm.raw_file_url,
                file_size=orm.file_size,
                file_type=orm.file_type,
                status=orm.status,
                error_msg=orm.error_msg,
                retry_count=orm.retry_count,
                created_by=orm.created_by,
                uploaded_at=orm.uploaded_at,
                updated_at=orm.updated_at,
            )

    async def get_document_by_hash(self, content_hash: str) -> DocumentRecord | None:
        async with self._session_factory() as session:
            result = await session.execute(select(DocumentORM).where(DocumentORM.content_hash == content_hash))
            orm = result.scalar_one_or_none()
            if orm is None:
                return None
            return DocumentRecord(
                doc_id=orm.doc_id,
                dataset_id=orm.dataset_id,
                content_hash=orm.content_hash,
                filename=orm.filename,
                raw_file_url=orm.raw_file_url,
                file_size=orm.file_size,
                file_type=orm.file_type,
                status=orm.status,
                error_msg=orm.error_msg,
                retry_count=orm.retry_count,
                created_by=orm.created_by,
                uploaded_at=orm.uploaded_at,
                updated_at=orm.updated_at,
            )

    async def update_document_for_reingest(self, doc_id: str, filename: str, file_size: int, raw_file_url: str) -> None:
        """重置文档记录以重新摄入：更新文件信息，重置状态"""
        async with self._session_factory() as session:
            stmt = (
                update(DocumentORM)
                .where(DocumentORM.doc_id == doc_id)
                .values(
                    filename=filename,
                    file_size=file_size,
                    raw_file_url=raw_file_url,
                    status="pending",
                    error_msg=None,
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def list_documents(self, page: int = 1, size: int = 20) -> tuple[list[DocumentRecord], int]:
        async with self._session_factory() as session:
            # 总数
            count_result = await session.execute(select(func.count()).select_from(DocumentORM))
            total = count_result.scalar() or 0

            # 分页查询
            result = await session.execute(
                select(DocumentORM).order_by(DocumentORM.uploaded_at.desc()).offset((page - 1) * size).limit(size)
            )
            rows = result.scalars().all()
            records = [
                DocumentRecord(
                    doc_id=r.doc_id,
                    dataset_id=r.dataset_id,
                    content_hash=r.content_hash,
                    filename=r.filename,
                    raw_file_url=r.raw_file_url,
                    file_size=r.file_size,
                    file_type=r.file_type,
                    status=r.status,
                    error_msg=r.error_msg,
                    retry_count=r.retry_count,
                    created_by=r.created_by,
                    uploaded_at=r.uploaded_at,
                    updated_at=r.updated_at,
                )
                for r in rows
            ]
            return records, total

    async def save_chunk(self, chunk: ChunkRecord) -> None:
        async with self._session_factory() as session:
            orm = ChunkORM(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                chunk_type=chunk.chunk_type,
                full_text=chunk.full_text,
                elements=[e for e in chunk.elements],
                image_urls=chunk.image_urls,
                page=chunk.page,
                chunk_index=chunk.chunk_index,
                char_count=chunk.char_count,
                group_id=chunk.group_id,
            )
            session.add(orm)
            await session.commit()

    async def save_chunks_batch(self, chunks: list[ChunkRecord]) -> None:
        async with self._session_factory() as session:
            orm_list = [
                ChunkORM(
                    chunk_id=c.chunk_id,
                    doc_id=c.doc_id,
                    chunk_type=c.chunk_type,
                    full_text=c.full_text,
                    elements=[e for e in c.elements],
                    image_urls=c.image_urls,
                    page=c.page,
                    chunk_index=c.chunk_index,
                    char_count=c.char_count,
                    group_id=c.group_id,
                )
                for c in chunks
            ]
            session.add_all(orm_list)
            await session.commit()

    async def delete_chunks_by_doc(self, doc_id: str) -> int:
        async with self._session_factory() as session:
            stmt = delete(ChunkORM).where(ChunkORM.doc_id == doc_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    @staticmethod
    def _chunk_orm_to_record(orm: ChunkORM) -> ChunkRecord:
        return ChunkRecord(
            chunk_id=orm.chunk_id,
            doc_id=orm.doc_id,
            chunk_type=orm.chunk_type,
            full_text=orm.full_text,
            elements=orm.elements if isinstance(orm.elements, list) else [],
            image_urls=orm.image_urls if isinstance(orm.image_urls, list) else [],
            page=orm.page,
            chunk_index=orm.chunk_index,
            char_count=orm.char_count,
            group_id=orm.group_id,
            created_at=orm.created_at,
        )

    async def get_chunk(self, chunk_id: str) -> ChunkRecord | None:
        async with self._session_factory() as session:
            result = await session.execute(select(ChunkORM).where(ChunkORM.chunk_id == chunk_id))
            orm = result.scalar_one_or_none()
            if orm is None:
                return None
            return self._chunk_orm_to_record(orm)

    async def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[ChunkRecord]:
        async with self._session_factory() as session:
            result = await session.execute(select(ChunkORM).where(ChunkORM.chunk_id.in_(chunk_ids)))
            rows = result.scalars().all()
            return [self._chunk_orm_to_record(r) for r in rows]

    async def list_chunks_by_doc(self, doc_id: str, page: int = 1, size: int = 20) -> tuple[list[ChunkRecord], int]:
        async with self._session_factory() as session:
            count_result = await session.execute(
                select(func.count()).select_from(ChunkORM).where(ChunkORM.doc_id == doc_id)
            )
            total = count_result.scalar() or 0

            result = await session.execute(
                select(ChunkORM)
                .where(ChunkORM.doc_id == doc_id)
                .order_by(ChunkORM.page.asc(), ChunkORM.chunk_index.asc())
                .offset((page - 1) * size)
                .limit(size)
            )
            rows = result.scalars().all()
            records = [self._chunk_orm_to_record(r) for r in rows]
            return records, total

    async def delete_chunks_by_ids(self, chunk_ids: list[str]) -> int:
        async with self._session_factory() as session:
            stmt = delete(ChunkORM).where(ChunkORM.chunk_id.in_(chunk_ids))
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    async def save_query_log(self, log: QueryLogRecord) -> None:
        async with self._session_factory() as session:
            orm = QueryLogORM(
                log_id=log.log_id,
                question=log.question,
                answer=log.answer,
                retrieved_chunks=log.retrieved_chunks,
                retrieval_ms=log.retrieval_ms,
                llm_ms=log.llm_ms,
                total_ms=log.total_ms,
                token_count=log.token_count,
                cache_hit=log.cache_hit,
                created_by=log.created_by,
            )
            session.add(orm)
            await session.commit()

    async def clear_group_id(self, group_ids: list[str]) -> int:
        async with self._session_factory() as session:
            stmt = update(ChunkORM).where(ChunkORM.group_id.in_(group_ids)).values(group_id="")
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    async def update_chunks_group_id(self, chunk_ids: list[str], group_id: str) -> int:
        async with self._session_factory() as session:
            stmt = update(ChunkORM).where(ChunkORM.chunk_id.in_(chunk_ids)).values(group_id=group_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    async def clear_group_ids_by_ids(self, chunk_ids: list[str]) -> int:
        async with self._session_factory() as session:
            stmt = update(ChunkORM).where(ChunkORM.chunk_id.in_(chunk_ids)).values(group_id="")
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    async def update_chunk_full_text(self, chunk_id: str, full_text: str, char_count: int) -> bool:
        async with self._session_factory() as session:
            stmt = update(ChunkORM).where(ChunkORM.chunk_id == chunk_id).values(full_text=full_text, char_count=char_count)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    # ---- 数据集管理 ----

    @staticmethod
    def _dataset_orm_to_record(orm: DatasetORM) -> DatasetRecord:
        return DatasetRecord(
            dataset_id=orm.dataset_id,
            name=orm.name,
            description=orm.description,
            created_by=orm.created_by,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def create_dataset(
        self,
        dataset_id: str,
        name: str,
        description: str | None = None,
        created_by: str | None = None,
    ) -> DatasetRecord:
        async with self._session_factory() as session:
            orm = DatasetORM(
                dataset_id=dataset_id,
                name=name,
                description=description,
                created_by=created_by,
            )
            session.add(orm)
            await session.commit()
            await session.refresh(orm)
            return self._dataset_orm_to_record(orm)

    async def get_dataset(self, dataset_id: str) -> DatasetRecord | None:
        async with self._session_factory() as session:
            result = await session.execute(select(DatasetORM).where(DatasetORM.dataset_id == dataset_id))
            orm = result.scalar_one_or_none()
            if orm is None:
                return None
            return self._dataset_orm_to_record(orm)

    async def list_datasets(self, page: int = 1, size: int = 20) -> tuple[list[DatasetRecord], int]:
        async with self._session_factory() as session:
            count_result = await session.execute(select(func.count()).select_from(DatasetORM))
            total = count_result.scalar() or 0

            result = await session.execute(
                select(DatasetORM).order_by(DatasetORM.created_at.desc()).offset((page - 1) * size).limit(size)
            )
            rows = result.scalars().all()
            records = [self._dataset_orm_to_record(r) for r in rows]
            return records, total

    async def update_dataset(
        self,
        dataset_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> DatasetRecord | None:
        async with self._session_factory() as session:
            values = {}
            if name is not None:
                values["name"] = name
            if description is not None:
                values["description"] = description
            if not values:
                return await self.get_dataset(dataset_id)

            stmt = update(DatasetORM).where(DatasetORM.dataset_id == dataset_id).values(**values)
            await session.execute(stmt)
            await session.commit()

        return await self.get_dataset(dataset_id)

    async def delete_document(self, doc_id: str) -> bool:
        async with self._session_factory() as session:
            stmt = delete(DocumentORM).where(DocumentORM.doc_id == doc_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def delete_dataset(self, dataset_id: str) -> bool:
        async with self._session_factory() as session:
            stmt = delete(DatasetORM).where(DatasetORM.dataset_id == dataset_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def count_docs_by_dataset(self, dataset_id: str) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.count()).select_from(DocumentORM).where(DocumentORM.dataset_id == dataset_id)
            )
            return result.scalar() or 0

    async def get_doc_ids_by_dataset_ids(self, dataset_ids: list[str]) -> list[str]:
        async with self._session_factory() as session:
            result = await session.execute(select(DocumentORM.doc_id).where(DocumentORM.dataset_id.in_(dataset_ids)))
            return [row[0] for row in result.all()]

    async def get_doc_ids_by_filenames(self, filenames: list[str]) -> list[str]:
        async with self._session_factory() as session:
            conditions = [DocumentORM.filename.ilike(f"%{name}%") for name in filenames]
            result = await session.execute(select(DocumentORM.doc_id).where(or_(*conditions)))
            return [row[0] for row in result.all()]
