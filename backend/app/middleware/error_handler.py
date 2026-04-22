import logging
import traceback

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

logger = logging.getLogger("app.error_handler")


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            # In production, log minimal info — full traces only in development
            if settings.is_production:
                logger.error("Unhandled exception on %s %s", request.method, request.url.path, exc_info=True)
            else:
                logger.error(
                    "Unhandled exception on %s %s:\n%s",
                    request.method,
                    request.url.path,
                    traceback.format_exc(),
                )
            return JSONResponse(
                status_code=500,
                content={"detail": "Dogodila se neočekivana greška."},
            )
