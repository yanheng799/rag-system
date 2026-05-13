"""MinIO 对象存储实现"""

from __future__ import annotations

import io
import logging
from datetime import timedelta
from typing import Optional

from minio import Minio
from minio.error import S3Error

from src.config.settings import settings
from src.storage.ports import ObjectStorePort

logger = logging.getLogger(__name__)


class OSSStore(ObjectStorePort):
    """MinIO 对象存储实现"""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        bucket: Optional[str] = None,
        secure: Optional[bool] = None,
    ):
        self._endpoint = endpoint or settings.minio_endpoint
        self._access_key = access_key or settings.minio_access_key
        self._secret_key = secret_key or settings.minio_secret_key
        self._bucket = bucket or settings.minio_bucket
        self._secure = secure if secure is not None else settings.minio_secure
        self._client = Minio(
            self._endpoint,
            access_key=self._access_key,
            secret_key=self._secret_key,
            secure=self._secure,
        )

    def ensure_bucket(self) -> None:
        """确保 Bucket 存在"""
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)
            logger.info("MinIO Bucket '%s' 创建成功", self._bucket)
        else:
            logger.info("MinIO Bucket '%s' 已存在", self._bucket)

    def upload_raw_doc(self, doc_id: str, filename: str, data: bytes) -> str:
        """上传原始文档至 /raw-docs/{doc_id}/{filename}"""
        object_name = f"raw-docs/{doc_id}/{filename}"
        self._client.put_object(
            self._bucket,
            object_name,
            io.BytesIO(data),
            length=len(data),
        )
        logger.info("原始文档已上传: %s", object_name)
        return object_name

    def upload_table_image(
        self, doc_id: str, page: int, table_index: int, image: bytes
    ) -> str:
        """上传表格截图至 /table-images/{doc_id}_p{page}_t{table_index}.png"""
        object_name = f"table-images/{doc_id}_p{page}_t{table_index}.png"
        self._client.put_object(
            self._bucket,
            object_name,
            io.BytesIO(image),
            length=len(image),
            content_type="image/png",
        )
        logger.info("表格截图已上传: %s", object_name)
        return object_name

    def upload_doc_image(
        self, doc_id: str, page: int, image_index: int, image: bytes, ext: str = "png"
    ) -> str:
        """上传文档图片至 /doc-images/{doc_id}_p{page}_img{image_index}.{ext}"""
        object_name = f"doc-images/{doc_id}_p{page}_img{image_index}.{ext}"
        content_type = f"image/{ext}" if ext != "jpg" else "image/jpeg"
        self._client.put_object(
            self._bucket,
            object_name,
            io.BytesIO(image),
            length=len(image),
            content_type=content_type,
        )
        logger.info("文档图片已上传: %s", object_name)
        return object_name

    def sign_url(self, path: str, expire_seconds: int = 3600) -> str:
        """生成预签名访问 URL"""
        url = self._client.presigned_get_object(
            self._bucket, path, expires=timedelta(seconds=expire_seconds)
        )
        return url

    def download(self, path: str) -> bytes:
        """下载文件"""
        response = self._client.get_object(self._bucket, path)
        data = response.read()
        response.close()
        response.release_conn()
        return data

    def delete(self, path: str) -> None:
        """删除文件"""
        self._client.remove_object(self._bucket, path)
        logger.info("文件已删除: %s", path)
