"""文档管理路由：多文件上传、摄入、状态查询、删除"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
from datetime import UTC

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, Query

from src.api.schemas.documents import (
    DocumentListItem,
    DocumentListResponse,
    DocumentStatusResponse,
    IngestRequest,
    IngestResponse,
    IngestResult,
    UploadResponse,
)
from src.ingestion.pipeline import generate_doc_id

router = APIRouter(prefix="/api/v1/documents", tags=["文档管理"])

logger = logging.getLogger(__name__)


def _compute_content_hash(data: bytes) -> str:
    """计算文件内容的 SHA-256 哈希"""
    return hashlib.sha256(data).hexdigest()


def _get_ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


# ---- 多文件上传 ----


@router.post("", response_model=list[UploadResponse], summary="上传文档")
async def upload_documents(
    request: Request,
    files: list[UploadFile] = File(...),  # noqa: B008
    dataset_id: str | None = Form(None),
):
    """批量上传文档，保存至 OSS 并创建记录（status=pending），不触发解析。"""
    from src.config.settings import settings

    pg_store = request.app.state.pg_store
    oss_store = request.app.state.oss_store

    # 校验 dataset_id
    if dataset_id:
        ds = await pg_store.get_dataset(dataset_id)
        if ds is None:
            raise HTTPException(status_code=404, detail="数据集不存在")

    results: list[UploadResponse] = []

    for file in files:
        filename = file.filename or ""
        ext = _get_ext(filename)

        if ext not in settings.supported_file_types:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件格式: {ext}，支持: {settings.supported_file_types}",
            )

        file_data = await file.read()
        if len(file_data) > settings.max_file_size_mb * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"文件过大: {filename}，最大支持 {settings.max_file_size_mb}MB",
            )

        content_hash = _compute_content_hash(file_data)
        existing_doc = await pg_store.get_document_by_hash(content_hash)

        if existing_doc:
            # 重复文件 → 覆盖
            doc_id = existing_doc.doc_id
            raw_file_url = f"raw-docs/{doc_id}/{filename}"
            oss_store.upload_raw_doc(doc_id, filename, file_data)

            from src.storage.milvus_store import MilvusStore

            if isinstance(request.app.state.milvus_store, MilvusStore):
                request.app.state.milvus_store.delete_by_doc_id(doc_id)
            await pg_store.delete_chunks_by_doc(doc_id)
            await pg_store.update_document_for_reingest(
                doc_id=doc_id,
                filename=filename,
                file_size=len(file_data),
                raw_file_url=raw_file_url,
            )
        else:
            # 新文件
            doc_id = generate_doc_id()
            raw_file_url = f"raw-docs/{doc_id}/{filename}"
            oss_store.upload_raw_doc(doc_id, filename, file_data)

            from src.models.documents import DocumentRecord

            await pg_store.save_document(
                DocumentRecord(
                    doc_id=doc_id,
                    dataset_id=dataset_id,
                    content_hash=content_hash,
                    filename=filename,
                    raw_file_url=raw_file_url,
                    file_size=len(file_data),
                    file_type=ext,
                )
            )

        uploaded_at = __import__("datetime").datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        results.append(
            UploadResponse(
                doc_id=doc_id,
                filename=filename,
                dataset_id=dataset_id,
                status="pending",
                uploaded_at=uploaded_at,
            )
        )
        logger.info("文档上传完成: doc_id=%s, filename=%s", doc_id, filename)

    return results


# ---- 文档列表 ----


@router.get("", response_model=DocumentListResponse, summary="文档列表")
async def list_documents(
    request: Request,
    dataset_id: str | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
):
    """分页查询文档列表，可按 dataset_id 过滤"""
    pg_store = request.app.state.pg_store
    records, total = await pg_store.list_documents(page=page, size=size, dataset_id=dataset_id)

    items = [
        DocumentListItem(
            doc_id=r.doc_id,
            filename=r.filename,
            status=r.status,
            error_msg=r.error_msg,
            uploaded_at=r.uploaded_at.isoformat() if r.uploaded_at else None,
            updated_at=r.updated_at.isoformat() if r.updated_at else None,
        )
        for r in records
    ]
    return DocumentListResponse(total=total, page=page, size=size, items=items)


# ---- 摄入（解析 + 向量化）----


@router.post("/ingest", response_model=IngestResponse, summary="摄入文档")
async def ingest_documents(request: Request, body: IngestRequest):
    """对指定文档执行解析和向量化。仅处理 status=pending 的文档。"""
    pg_store = request.app.state.pg_store
    oss_store = request.app.state.oss_store
    milvus_store = request.app.state.milvus_store
    embedder = request.app.state.embedder

    from src.ingestion.pipeline import IngestionPipeline

    pipeline = IngestionPipeline(
        vector_store=milvus_store,
        doc_store=pg_store,
        oss_store=oss_store,
        embedder=embedder,
    )

    results: list[IngestResult] = []

    for doc_id in body.doc_ids:
        doc = await pg_store.get_document(doc_id)
        if doc is None:
            results.append(IngestResult(doc_id=doc_id, filename="", status="failed", error_msg="文档不存在"))
            continue

        if doc.status not in ("pending", "failed"):
            results.append(
                IngestResult(
                    doc_id=doc_id,
                    filename=doc.filename,
                    status=doc.status,
                    error_msg=f"文档状态为 {doc.status}，无法摄入",
                )
            )
            continue

        # 从 OSS 下载到临时文件
        tmp_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_path = os.path.join(tmp_dir, f"{doc_id}.{doc.file_type}")

        try:
            file_data = oss_store.download(doc.raw_file_url)
            with open(tmp_path, "wb") as f:
                f.write(file_data)

            await pipeline.ingest(doc_id, tmp_path, doc.file_type, skip_oss_upload=True)

            updated_doc = await pg_store.get_document(doc_id)
            results.append(
                IngestResult(
                    doc_id=doc_id,
                    filename=doc.filename,
                    status=updated_doc.status if updated_doc else "failed",
                    error_msg=updated_doc.error_msg if updated_doc else None,
                )
            )
        except Exception as e:
            logger.exception("文档摄入失败: doc_id=%s", doc_id)
            results.append(IngestResult(doc_id=doc_id, filename=doc.filename, status="failed", error_msg=str(e)))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    return IngestResponse(results=results)


# ---- 删除文档 ----


@router.delete("/{doc_id}", summary="删除文档")
async def delete_document(request: Request, doc_id: str):
    """删除文档及其关联的向量、分块记录和 OSS 文件"""
    pg_store = request.app.state.pg_store
    milvus_store = request.app.state.milvus_store
    oss_store = request.app.state.oss_store

    doc = await pg_store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    milvus_store.delete_by_doc_id(doc_id)
    await pg_store.delete_chunks_by_doc(doc_id)

    if doc.raw_file_url:
        with contextlib.suppress(Exception):
            oss_store.delete(doc.raw_file_url)

    await pg_store.delete_document(doc_id)

    return {"message": "删除成功", "doc_id": doc_id}


# ---- 查询状态 ----


@router.get("/{doc_id}/status", response_model=DocumentStatusResponse, summary="查询文档状态")
async def get_document_status(request: Request, doc_id: str):
    """查询文档处理状态"""
    pg_store = request.app.state.pg_store
    doc = await pg_store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    return DocumentStatusResponse(
        doc_id=doc.doc_id,
        filename=doc.filename,
        status=doc.status,
        error_msg=doc.error_msg,
        uploaded_at=doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        updated_at=doc.updated_at.isoformat() if doc.updated_at else None,
    )
