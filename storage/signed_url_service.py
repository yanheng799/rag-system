"""签名 URL 服务：统一管理 image_url 的签名替换"""

from __future__ import annotations

from storage.ports import ObjectStorePort


class SignedUrlService:
    """将内部 OSS 路径替换为签名 URL"""

    def __init__(self, oss_store: ObjectStorePort, expire_seconds: int = 3600):
        self._oss = oss_store
        self._expire_seconds = expire_seconds

    def sign(self, internal_path: str) -> str:
        """将内部路径转换为签名 URL"""
        if not internal_path:
            return internal_path
        return self._oss.sign_url(internal_path, self._expire_seconds)

    def sign_elements(self, elements: list[dict]) -> list[dict]:
        """批量替换 elements 中的 image_url"""
        for elem in elements:
            if elem.get("image_url"):
                elem["image_url"] = self.sign(elem["image_url"])
        return elements
