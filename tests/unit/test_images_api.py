"""图片代理 API 测试"""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.images import router, IMAGE_CONTENT_TYPES


class _FakeOssStore:
    """轻量 Fake：记录下载请求，返回预设数据"""

    def __init__(self, files: dict[str, bytes] | None = None):
        self._files = files or {}
        self.downloaded_paths: list[str] = []

    def download(self, path: str) -> bytes:
        self.downloaded_paths.append(path)
        if path not in self._files:
            raise FileNotFoundError(path)
        return self._files[path]


class _FakePgStore:
    """轻量 Fake：模拟 PG 文档查询"""
    def __init__(self, docs: dict[str, object] | None = None):
        self._docs = docs or {}

    async def get_document(self, doc_id: str):
        return self._docs.get(doc_id)


def _make_app(oss_store=None, pg_store=None) -> tuple[FastAPI, TestClient]:
    app = FastAPI()
    app.state.oss_store = oss_store or _FakeOssStore()
    app.state.pg_store = pg_store or _FakePgStore()
    app.include_router(router)
    return app, TestClient(app)


_auth_disabled = patch("src.api.deps.settings.auth_enabled", False)


# ---- 正常返回图片 ----


@_auth_disabled
class TestImageProxy:
    """GET /api/v1/images/{path} 代理转发图片"""

    def test_png_image_returned(self):
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        oss = _FakeOssStore({"doc-images/test.png": png_data})
        _, client = _make_app(oss)

        resp = client.get("/api/v1/images/doc-images/test.png")
        assert resp.status_code == 200
        assert resp.content == png_data
        assert resp.headers["content-type"] == "image/png"

    def test_jpg_image_returned(self):
        jpg_data = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        oss = _FakeOssStore({"doc-images/photo.jpg": jpg_data})
        _, client = _make_app(oss)

        resp = client.get("/api/v1/images/doc-images/photo.jpg")
        assert resp.status_code == 200
        assert resp.content == jpg_data
        assert resp.headers["content-type"] == "image/jpeg"

    def test_table_screenshot_returned(self):
        data = b"table-image-data"
        oss = _FakeOssStore({"table-images/doc_001_p3_t1.png": data})
        _, client = _make_app(oss)

        resp = client.get("/api/v1/images/table-images/doc_001_p3_t1.png")
        assert resp.status_code == 200
        assert resp.content == data

    def test_nested_path(self):
        data = b"nested"
        oss = _FakeOssStore({"raw-docs/doc_001/report.pdf": data})
        _, client = _make_app(oss)

        resp = client.get("/api/v1/images/raw-docs/doc_001/report.pdf")
        assert resp.status_code == 200

    def test_unknown_extension_returns_octet_stream(self):
        data = b"unknown"
        oss = _FakeOssStore({"files/data.xyz": data})
        _, client = _make_app(oss)

        resp = client.get("/api/v1/images/files/data.xyz")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/octet-stream"


# ---- 404 不存在的图片 ----


@_auth_disabled
class TestImageProxyNotFound:

    def test_missing_image_returns_404(self):
        oss = _FakeOssStore({})
        _, client = _make_app(oss)

        resp = client.get("/api/v1/images/nonexistent.png")
        assert resp.status_code == 404

    def test_404_detail_message(self):
        oss = _FakeOssStore({})
        _, client = _make_app(oss)

        resp = client.get("/api/v1/images/nonexistent.png")
        assert "不存在" in resp.json()["detail"]


# ---- Content-Type 映射 ----


class TestImageContentTypes:

    def test_all_mapped_extensions(self):
        assert IMAGE_CONTENT_TYPES["png"] == "image/png"
        assert IMAGE_CONTENT_TYPES["jpg"] == "image/jpeg"
        assert IMAGE_CONTENT_TYPES["jpeg"] == "image/jpeg"
        assert IMAGE_CONTENT_TYPES["gif"] == "image/gif"
        assert IMAGE_CONTENT_TYPES["webp"] == "image/webp"
        assert IMAGE_CONTENT_TYPES["svg"] == "image/svg+xml"
