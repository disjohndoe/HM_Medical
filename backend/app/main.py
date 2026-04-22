import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.agent_ws import router as agent_ws_router
from app.api.auth import limiter
from app.api.router import api_router
from app.config import settings
from app.middleware.error_handler import ErrorHandlerMiddleware
from app.middleware.request_logger import RequestLoggerMiddleware
from app.services.cezih.exceptions import CezihError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses. In production, Caddy handles this;
    this ensures dev environments also have protection."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=63072000; includeSubDomains; preload",
            )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.halmed_sync_service import start_sync_scheduler, stop_sync_scheduler
    from app.services.icd10_sync_service import start_icd10_sync_scheduler, stop_icd10_sync_scheduler

    app.state.http_client = httpx.AsyncClient(timeout=settings.CEZIH_TIMEOUT)
    start_sync_scheduler()
    start_icd10_sync_scheduler()
    yield
    stop_icd10_sync_scheduler()
    stop_sync_scheduler()
    await app.state.http_client.aclose()


app = FastAPI(
    title="HM Digital Medical MVP",
    description="API za upravljanje pacijentima poliklinike",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda r, e: _rate_limit_exceeded_handler(r, e))  # type: ignore[arg-type]


@app.exception_handler(CezihError)
async def cezih_error_handler(request: Request, exc: CezihError) -> JSONResponse:
    """Safety net for any CezihError that escapes the dispatcher's
    _raise_cezih_error. Produces the same structured body the frontend
    CezihApiError parser expects (detail.message + detail.cezih_error)."""
    logging.getLogger("app.cezih").warning(
        "CEZIH error on %s %s: %s (%s)",
        request.method,
        request.url.path,
        exc.__class__.__name__,
        exc.message,
    )
    return JSONResponse(
        status_code=exc.http_status_code,
        content={
            "detail": {
                "message": exc.message,
                "cezih_error": exc.to_operation_outcome(),
            },
        },
    )


app.add_middleware(RequestLoggerMiddleware)
app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    expose_headers=["Content-Disposition", "X-Pdf-Digitally-Signed", "X-Pdf-Unsigned-Reason"],
)

app.include_router(api_router, prefix="/api")
app.include_router(agent_ws_router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": settings.APP_VERSION}
