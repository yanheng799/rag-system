"""图片代理路由：根据内部 OSS 路径返回图片，无需签名"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import Response

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
async def get_image(request: Request, path: str):
    """根据内部 OSS 路径返回图片"""
    oss_store = request.app.state.oss_store

    try:
        data = oss_store.download(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"图片不存在: {path}")

    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    content_type = IMAGE_CONTENT_TYPES.get(ext, "application/octet-stream")

    return Response(content=data, media_type=content_type)
