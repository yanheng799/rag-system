"""全局错误处理中间件"""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """统一异常捕获，返回标准 JSON 错误响应"""

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            # 记录完整堆栈，避免 500 变成无栈信息的黑盒（此前丢失了真实异常原因）
            logger.exception("未处理异常: %s %s", request.method, request.url.path)
            return JSONResponse(
                status_code=500,
                content={"detail": f"内部服务器错误: {exc!s}"},
            )
