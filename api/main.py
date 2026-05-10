"""FastAPI 应用入口 — 手动 DI 组装"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse

from api.middleware.error_handler import ErrorHandlerMiddleware
from api.routers import debug, documents, query
from config.settings import settings
from ingestion.embedder import Embedder
from ingestion.parsers.registry import init_parsers
from orchestration.llm_client import QwenClient
from orchestration.orchestrator import RAGOrchestrator
from orchestration.prompt_builder import PromptBuilder
from retrieval.vector_search import VectorSearcher
from storage.milvus_store import MilvusStore
from storage.oss_store import OSSStore
from storage.pg_store import PgStore
from storage.signed_url_service import SignedUrlService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时组装组件，关闭时释放资源"""
    logger.info("初始化 RAG 系统...")

    # 注册解析器
    init_parsers()

    # 存储层组件
    pg_store = PgStore()
    milvus_store = MilvusStore()
    oss_store = OSSStore()
    oss_store.ensure_bucket()

    # 初始化 Milvus Collection
    milvus_store.init_collection()

    # 签名 URL 服务
    signed_url_service = SignedUrlService(oss_store)

    # Embedder
    embedder = Embedder()

    # 向量检索
    vector_searcher = VectorSearcher(
        vector_store=milvus_store,
        embedder=embedder,
    )

    # LLM 客户端
    llm_client = QwenClient()

    # Prompt 构建器
    prompt_builder = PromptBuilder()

    # 编排器
    orchestrator = RAGOrchestrator(
        vector_searcher=vector_searcher,
        llm_client=llm_client,
        prompt_builder=prompt_builder,
        doc_store=pg_store,
        signed_url_service=signed_url_service,
    )

    # 组件注入到 app.state
    app.state.pg_store = pg_store
    app.state.milvus_store = milvus_store
    app.state.oss_store = oss_store
    app.state.signed_url_service = signed_url_service
    app.state.embedder = embedder
    app.state.vector_searcher = vector_searcher
    app.state.llm_client = llm_client
    app.state.orchestrator = orchestrator

    logger.info("RAG 系统初始化完成")

    yield

    logger.info("RAG 系统关闭")


app = FastAPI(
    title="RAG 问答系统",
    description="电力工程领域 RAG（检索增强生成）系统 API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

# 中间件
app.add_middleware(ErrorHandlerMiddleware)

# 路由注册
app.include_router(documents.router)
app.include_router(query.router)
app.include_router(debug.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/docs", include_in_schema=False)
async def custom_docs():
    """自包含 Swagger UI 页面，不依赖外部 CDN"""
    return HTMLResponse(content=_build_docs_html())


def _build_docs_html() -> str:
    """构建内联 Swagger UI 的 HTML，使用 unpkg CDN 并提供多个 fallback"""
    return """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>RAG 问答系统 - API 文档</title>
    <style>
        body { margin: 0; background: #fafafa; }
        .loading { display:flex; justify-content:center; align-items:center; height:100vh; font-family:sans-serif; color:#666; }
    </style>
</head>
<body>
<div id="swagger-ui"></div>
<div class="loading" id="loading">加载 API 文档中...</div>
<script>
// CDN 源列表，按优先级尝试
const CDN_SOURCES = [
    { css: 'https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css',
      js:  'https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js' },
    { css: 'https://unpkg.com/swagger-ui-dist@5/swagger-ui.css',
      js:  'https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js' },
    { css: 'https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.11.0/swagger-ui.css',
      js:  'https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.11.0/swagger-ui-bundle.js' },
];

async function tryLoad(src) {
    const resp = await fetch(src, { mode: 'cors' });
    if (!resp.ok) throw new Error(resp.status);
    return resp.text();
}

function loadCSS(href) {
    return new Promise((resolve, reject) => {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.type = 'text/css';
        link.href = href;
        link.onload = resolve;
        link.onerror = reject;
        document.head.appendChild(link);
    });
}

function execJS(code) {
    const s = document.createElement('script');
    s.textContent = code;
    document.head.appendChild(s);
}

async function init() {
    for (const cdn of CDN_SOURCES) {
        try {
            await loadCSS(cdn.css);
            const jsCode = await tryLoad(cdn.js);
            execJS(jsCode);
            document.getElementById('loading').style.display = 'none';
            SwaggerUIBundle({
                url: location.origin + '/openapi.json',
                dom_id: '#swagger-ui',
                layout: 'BaseLayout',
                deepLinking: true,
                presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
            });
            return;
        } catch (e) {
            console.warn('CDN 加载失败:', cdn.js, e);
        }
    }
    document.getElementById('loading').innerHTML =
        '<div style="text-align:center"><h3>无法加载 Swagger UI</h3>' +
        '<p>所有 CDN 源均不可用，请检查网络连接</p>' +
        '<p>可直接访问 <a href="/openapi.json">/openapi.json</a> 查看 API 定义</p></div>';
}
init();
</script>
</body>
</html>"""


if __name__ == "__main__":
      import uvicorn
      uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)