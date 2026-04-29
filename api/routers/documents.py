"""文档管理路由：上传、状态查询"""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, HTTPException, Request, UploadFile, File

from api.schemas.documents import DocumentStatusResponse, UploadResponse
from ingestion.pipeline import generate_doc_id

router = APIRouter(prefix="/api/v1/documents", tags=["文档管理"])


@router.post("", response_model=UploadResponse, summary="上传文档")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
):
    """上传文档，触发同步摄入流程"""
    # 验证文件类型
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    from config.settings import settings

    if ext not in settings.supported_file_types:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {ext}，支持: {settings.supported_file_types}",
        )

    # 读取文件
    file_data = await file.read()
    if len(file_data) > settings.max_file_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，最大支持 {settings.max_file_size_mb}MB",
        )

    doc_id = generate_doc_id()

    # 保存临时文件
    from config.settings import settings as s

    tmp_dir = os.path.join(os.path.dirname(__file__), "..", "..", "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f"{doc_id}.{ext}")
    with open(tmp_path, "wb") as f:
        f.write(file_data)

    # 创建文档记录
    from models.documents import DocumentRecord

    doc_record = DocumentRecord(
        doc_id=doc_id,
        filename=filename,
        raw_file_url=f"raw-docs/{doc_id}/{filename}",
        file_size=len(file_data),
        file_type=ext,
    )

    # 获取存储组件
    pg_store = request.app.state.pg_store
    oss_store = request.app.state.oss_store
    milvus_store = request.app.state.milvus_store

    from ingestion.embedder import Embedder
    from ingestion.pipeline import IngestionPipeline

    embedder = Embedder()
    pipeline = IngestionPipeline(
        vector_store=milvus_store,
        doc_store=pg_store,
        oss_store=oss_store,
        embedder=embedder,
    )

    # 保存文档记录
    await pg_store.save_document(doc_record)

    # 执行摄入
    from datetime import datetime, timezone

    uploaded_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        await pipeline.ingest(doc_id, tmp_path, ext)
    except Exception as e:
        # 摄入失败已在 pipeline 内部处理状态更新
        pass
    finally:
        # 清理临时文件
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return UploadResponse(
        doc_id=doc_id,
        filename=filename,
        status="done",
        uploaded_at=uploaded_at,
    )


@router.get(
    "/{doc_id}/status", response_model=DocumentStatusResponse, summary="查询文档状态"
)
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
