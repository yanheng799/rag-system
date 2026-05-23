"""统一配置管理，基于 pydantic-settings，支持 .env 文件和环境变量覆盖"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    embedding_model: str = Field(default="bge-large-zh-v1.5", description="Embedding 模型名称")
    embedding_base_url: str = Field(
        default="http://127.0.0.1:8001/v1", description="Embedding 服务地址（OpenAI 兼容）"
    )
    embedding_api_key: str = Field(default="placeholder", description="Embedding 服务 API Key")
    embedding_dimension: int = Field(default=1024, description="Embedding 向量维度")
    embedding_batch_size: int = Field(default=10, description="Embedding 批量大小")
    embedding_max_input_length: int = Field(default=800, description="Embedding 单条文本最大字符数")
    embedding_query_prefix: str = Field(
        default="为这个句子生成表示以用于检索相关文章：",
        description="检索查询时的前缀指令（部分模型需要，如 bge 系列）",
    )

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
        default=["pdf", "docx", "xlsx", "txt", "md", "csv"],
        description="支持的文件类型",
    )

    # 分块配置
    chunk_max_size: int = Field(default=1024, description="最大分块字符数")
    chunk_vertical_gap: float = Field(default=15.0, description="段落垂直间距阈值(px)")

    # 检索配置
    default_top_k: int = Field(default=5, description="默认返回结果数")
    retrieval_top_k: int = Field(default=50, description="粗召回数量")
    rerank_top_k: int = Field(default=5, description="重排序后保留数量")

    # BM25 配置
    bm25_k1: float = Field(default=1.2, description="BM25 k1 参数，控制词频饱和度")
    bm25_b: float = Field(default=0.75, description="BM25 b 参数，控制文档长度归一化")

    # 混合检索配置
    rrf_k: int = Field(default=60, description="RRF 融合常数 k")

    # Milvus 索引配置
    milvus_index_type: str = Field(default="HNSW")
    milvus_metric_type: str = Field(default="COSINE")
    milvus_hnsw_m: int = Field(default=16)
    milvus_hnsw_ef_construction: int = Field(default=200)

    # JWT 配置
    jwt_secret: str = Field(default="change-me-in-production", description="JWT 签名密钥")
    jwt_expire_hours: int = Field(default=24, description="Token 有效期（小时）")
    auth_enabled: bool = Field(default=True, description="是否启用鉴权")

    # 签名 URL 配置
    signed_url_expire_seconds: int = Field(default=3600, description="签名 URL 有效期（秒）")

    # 查询改写配置
    query_rewrite_enabled: bool = Field(default=True, description="是否启用查询改写（多查询扩展）")
    query_rewrite_count: int = Field(default=3, description="查询改写生成的子查询数量")

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
