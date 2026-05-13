"""存储层抽象接口定义（StoragePort 模式）"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.models.documents import ChunkRecord, DatasetRecord, DocumentRecord, QueryLogRecord


class VectorStorePort(ABC):
    """向量数据库接口"""

    @abstractmethod
    def init_collection(self) -> None:
        """初始化 Collection（不存在则创建）"""

    @abstractmethod
    def insert(self, records: list[dict]) -> list[int]:
        """批量插入向量记录，返回主键 ID 列表"""

    @abstractmethod
    def search(
        self,
        embedding: list[float],
        top_k: int = 50,
        filters: dict | None = None,
    ) -> list[dict]:
        """向量检索，返回匹配结果列表"""

    @abstractmethod
    def delete_by_doc_id(self, doc_id: str) -> None:
        """按文档 ID 删除所有相关向量记录"""

    @abstractmethod
    def delete_by_chunk_ids(self, chunk_ids: list[str]) -> None:
        """按 chunk_id 列表删除指定向量记录"""

    @abstractmethod
    def fetch_by_group_ids(self, group_ids: list[str]) -> list[dict]:
        """按 group_id 批量查询所有关联分块"""


class DocumentStorePort(ABC):
    """文档/分块数据库接口"""

    @abstractmethod
    async def save_document(self, doc: DocumentRecord) -> None:
        """保存文档记录"""

    @abstractmethod
    async def update_status(self, doc_id: str, status: str, error_msg: str | None = None) -> None:
        """更新文档处理状态"""

    @abstractmethod
    async def get_document(self, doc_id: str) -> DocumentRecord | None:
        """查询文档记录"""

    @abstractmethod
    async def get_document_by_hash(self, content_hash: str) -> DocumentRecord | None:
        """按文件内容哈希查询文档记录"""

    @abstractmethod
    async def update_document_for_reingest(self, doc_id: str, filename: str, file_size: int, raw_file_url: str) -> None:
        """重置文档记录以重新摄入"""

    @abstractmethod
    async def list_documents(self, page: int = 1, size: int = 20) -> tuple[list[DocumentRecord], int]:
        """分页查询文档列表，返回 (记录列表, 总数)"""

    @abstractmethod
    async def save_chunk(self, chunk: ChunkRecord) -> None:
        """保存分块记录"""

    @abstractmethod
    async def save_chunks_batch(self, chunks: list[ChunkRecord]) -> None:
        """批量保存分块记录"""

    @abstractmethod
    async def delete_chunks_by_doc(self, doc_id: str) -> int:
        """删除文档下所有分块记录，返回删除数量"""

    @abstractmethod
    async def get_chunk(self, chunk_id: str) -> ChunkRecord | None:
        """查询单个分块记录"""

    @abstractmethod
    async def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[ChunkRecord]:
        """按 chunk_id 列表批量查询分块记录"""

    @abstractmethod
    async def list_chunks_by_doc(self, doc_id: str, page: int = 1, size: int = 20) -> tuple[list[ChunkRecord], int]:
        """分页查询文档下的分块列表，按 page + chunk_index 排序"""

    @abstractmethod
    async def delete_chunks_by_ids(self, chunk_ids: list[str]) -> int:
        """按 chunk_id 列表删除分块记录，返回删除数量"""

    @abstractmethod
    async def clear_group_id(self, group_ids: list[str]) -> int:
        """将指定 group_id 的所有分块的 group_id 清空，返回更新数量"""

    @abstractmethod
    async def update_chunks_group_id(self, chunk_ids: list[str], group_id: str) -> int:
        """按 chunk_id 列表更新分块的 group_id，返回更新数量"""

    @abstractmethod
    async def clear_group_ids_by_ids(self, chunk_ids: list[str]) -> int:
        """按 chunk_id 列表将分块的 group_id 清空，返回更新数量"""

    @abstractmethod
    async def save_query_log(self, log: QueryLogRecord) -> None:
        """保存查询日志"""

    # 数据集管理

    @abstractmethod
    async def create_dataset(
        self,
        dataset_id: str,
        name: str,
        description: str | None = None,
        created_by: str | None = None,
    ) -> DatasetRecord:
        """创建数据集"""

    @abstractmethod
    async def get_dataset(self, dataset_id: str) -> DatasetRecord | None:
        """查询数据集"""

    @abstractmethod
    async def list_datasets(self, page: int = 1, size: int = 20) -> tuple[list[DatasetRecord], int]:
        """分页查询数据集列表，返回 (记录列表, 总数)"""

    @abstractmethod
    async def update_dataset(
        self,
        dataset_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> DatasetRecord | None:
        """更新数据集名称或描述"""

    @abstractmethod
    async def delete_document(self, doc_id: str) -> bool:
        """删除文档记录"""

    @abstractmethod
    async def delete_dataset(self, dataset_id: str) -> bool:
        """删除数据集（不含级联逻辑，由路由层处理）"""

    @abstractmethod
    async def count_docs_by_dataset(self, dataset_id: str) -> int:
        """统计数据集下文档数量"""

    @abstractmethod
    async def get_doc_ids_by_dataset_ids(self, dataset_ids: list[str]) -> list[str]:
        """按数据集 ID 列表查询关联的文档 ID"""

    @abstractmethod
    async def get_doc_ids_by_filenames(self, filenames: list[str]) -> list[str]:
        """按文件名模糊匹配查询文档 ID"""


class ObjectStorePort(ABC):
    """对象存储接口"""

    @abstractmethod
    def ensure_bucket(self) -> None:
        """确保 Bucket 存在"""

    @abstractmethod
    def upload_raw_doc(self, doc_id: str, filename: str, data: bytes) -> str:
        """上传原始文档，返回内部路径"""

    @abstractmethod
    def upload_table_image(self, doc_id: str, page: int, table_index: int, image: bytes) -> str:
        """上传表格截图，返回内部路径"""

    @abstractmethod
    def upload_doc_image(self, doc_id: str, page: int, image_index: int, image: bytes, ext: str = "png") -> str:
        """上传文档图片，返回内部路径"""

    @abstractmethod
    def sign_url(self, path: str, expire_seconds: int = 3600) -> str:
        """生成签名访问 URL"""

    @abstractmethod
    def download(self, path: str) -> bytes:
        """下载文件内容"""

    @abstractmethod
    def delete(self, path: str) -> None:
        """删除文件"""


class CachePort(ABC):
    """缓存接口（Phase 4 激活）"""

    @abstractmethod
    async def get(self, key: str) -> str | None:
        """获取缓存值"""

    @abstractmethod
    async def set(self, key: str, value: str, ttl: int = 3600) -> None:
        """设置缓存值"""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """删除缓存"""
