"""全局错误处理中间件"""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """统一异常捕获，返回标准 JSON 错误响应"""

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            return JSONResponse(
                status_code=500,
                content={"detail": f"内部服务器错误: {str(exc)}"},
            )
