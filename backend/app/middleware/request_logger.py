import logging
import time

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("app.request_logger")

_SKIP_PATHS = {"/api/health", "/docs", "/openapi.json", "/redoc"}


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        # Log path only — never log query params (may contain patient_id, MBO, etc.)
        logger.info(
            "request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 1),
            },
        )
        return response
