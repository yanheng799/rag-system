"""图片代理路由：根据内部 OSS 路径返回图片，无需签名"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import Response

from src.api.deps import get_current_user

router = APIRouter(prefix="/api/v1", tags=["图片代理"])

IMAGE_CONTENT_TYPES: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "svg": "image/svg+xml",
    "pdf": "application/pdf",
}


@router.get("/images/{path:path}", summary="图片代理")
async def get_image(request: Request, path: str, user: dict = Depends(get_current_user)):
    """根据内部 OSS 路径返回图片，校验所属文档的 org_id"""
    oss_store = request.app.state.oss_store
    org_id = user.get("org_id", "") or ""

    # 校验图片所属文档的 org_id（仅在鉴权开启时）
    if org_id:
        import re
        match = re.match(r"(?:[^/]+/)?(?:raw-docs|table-images|doc-images)/([^/]+)/", path)
        if match:
            doc_id = match.group(1)
            pg_store = request.app.state.pg_store
            doc = await pg_store.get_document(doc_id)
            if doc is None or (doc.org_id and doc.org_id != org_id):
                raise HTTPException(status_code=404, detail=f"图片不存在: {path}")

    try:
        data = oss_store.download(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"图片不存在: {path}")

    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    content_type = IMAGE_CONTENT_TYPES.get(ext, "application/octet-stream")

    return Response(content=data, media_type=content_type)
