"""统一配置管理，基于 pydantic-settings，支持 .env 文件和环境变量覆盖"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # DashScope API
    dashscope_api_key: str = Field(default="sk-placeholder", description="DashScope API Key")

    # LLM 配置
    llm_model: str = Field(default="qwen3-max", description="LLM 模型名称")
    llm_base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1")
    llm_timeout: int = Field(default=30, description="LLM 请求超时（秒）")
    llm_max_tokens: int = Field(default=2048, description="LLM 最大输出 Token 数")
    llm_temperature: float = Field(default=0.1, description="LLM 温度参数")

    # Embedding 配置
    embedding_model: str = Field(default="text-embedding-v2")
    embedding_dimension: int = Field(default=1536, description="Embedding 向量维度")

    # PostgreSQL
    postgres_host: str = Field(default="127.0.0.1")
    postgres_port: int = Field(default=5432)
    postgres_user: str = Field(default="yanheng")
    postgres_password: str = Field(default="123456")
    postgres_db: str = Field(default="rag_system")

    # Milvus
    milvus_host: str = Field(default="127.0.0.1")
    milvus_port: int = Field(default=19530)
    milvus_collection: str = Field(default="rag_chunks")

    # MinIO
    minio_endpoint: str = Field(default="127.0.0.1:9000")
    minio_access_key: str = Field(default="minio")
    minio_secret_key: str = Field(default="miniosecret")
    minio_bucket: str = Field(default="rag-storage")
    minio_secure: bool = Field(default=False)

    # Redis (Phase 4 激活)
    redis_host: str = Field(default="127.0.0.1")
    redis_port: int = Field(default=6379)
    redis_password: str = Field(default="redis@123")
    redis_db: int = Field(default=0)

    # 摄入配置
    max_file_size_mb: int = Field(default=50, description="上传文件大小限制（MB）")
    supported_file_types: list[str] = Field(
        default=["pdf", "docx", "xlsx"],
        description="Phase 1 支持的文件类型",
    )

    # 分块配置
    chunk_max_size: int = Field(default=1024, description="最大分块字符数")
    chunk_vertical_gap: float = Field(default=15.0, description="段落垂直间距阈值(px)")

    # 检索配置
    default_top_k: int = Field(default=5, description="默认返回结果数")
    retrieval_top_k: int = Field(default=50, description="粗召回数量")
    rerank_top_k: int = Field(default=5, description="重排序后保留数量")

    # Milvus 索引配置
    milvus_index_type: str = Field(default="HNSW")
    milvus_metric_type: str = Field(default="COSINE")
    milvus_hnsw_m: int = Field(default=16)
    milvus_hnsw_ef_construction: int = Field(default=200)

    # 签名 URL 配置
    signed_url_expire_seconds: int = Field(default=3600, description="签名 URL 有效期（秒）")

    @property
    def postgres_dsn(self) -> str:
        """PostgreSQL 异步连接字符串"""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_sync_dsn(self) -> str:
        """PostgreSQL 同步连接字符串（Alembic 使用）"""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
