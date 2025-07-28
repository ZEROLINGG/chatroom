from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp
import logging


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = logging.getLogger("security_middleware")

    async def dispatch(self, request: Request, call_next):
        # 拒绝无效或恶意请求示例（可根据需要扩展）
        if not request.url.scheme in ("http", "https"):
            return Response("Invalid scheme", status_code=400)

        # 执行下一个中间件或视图
        response = await call_next(request)

        # 设置常见的安全响应头
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'"

        # 可选日志记录
        self.logger.info(f"Request from {request.client.host} to {request.url.path}")
        return response
