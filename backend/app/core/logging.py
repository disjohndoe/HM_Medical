"""Structured JSON logging with request-scoped context via ContextVars."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

# --- ContextVars: set per-request by middleware, read by formatters ---

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
tenant_id_ctx: ContextVar[str] = ContextVar("tenant_id", default="")
user_id_ctx: ContextVar[str] = ContextVar("user_id", default="")

# Standard LogRecord attributes — anything else in record.__dict__ came from `extra={}`.
_STD_LOGRECORD_ATTRS = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "taskName", "thread", "threadName",
    }
)


def _record_extras(record: logging.LogRecord) -> dict:
    """Return user-supplied extras: vanilla `extra={}` keys plus the wrapped `_extra` dict."""
    extras = {
        k: v
        for k, v in record.__dict__.items()
        if k not in _STD_LOGRECORD_ATTRS and not k.startswith("_")
    }
    wrapped = record.__dict__.get("_extra")
    if isinstance(wrapped, dict):
        extras.update(wrapped)
    return extras


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        obj: dict = {
            "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{record.msecs:03.0f}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Inject ContextVar fields when set
        for ctx, key in ((request_id_ctx, "request_id"), (tenant_id_ctx, "tenant_id"), (user_id_ctx, "user_id")):
            val = ctx.get("")
            if val:
                obj[key] = val

        # Merge extra fields (e.g. extra={"status_code": 200, "duration_ms": 42.3})
        obj.update(_record_extras(record))

        # Append exception info
        if record.exc_info and record.exc_info[1] is not None:
            obj["error"] = type(record.exc_info[1]).__name__
            obj["traceback"] = self.formatException(record.exc_info)

        return json.dumps(obj, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Human-readable format for local dev."""

    def format(self, record: logging.LogRecord) -> str:
        parts = [
            datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{record.msecs:03.0f}Z",
            f"{record.levelname:<8}",
            f"[{record.name}]",
        ]

        rid = request_id_ctx.get("")
        if rid:
            parts.append(f"[{rid[:8]}]")

        parts.append(record.getMessage())

        extras = _record_extras(record)
        if extras:
            parts.append("| " + " ".join(f"{k}={v}" for k, v in extras.items()))

        text = " ".join(parts)

        if record.exc_info and record.exc_info[1] is not None:
            text += "\n" + self.formatException(record.exc_info)

        return text


class _StructuredLoggerAdapter(logging.LoggerAdapter):
    """Redirect `extra={}` to `_extra` so JsonFormatter/TextFormatter pick it up."""

    def process(self, msg, kwargs):
        extra = kwargs.get("extra") or {}
        kwargs["extra"] = {"_extra": extra}
        return msg, kwargs


def get_logger(name: str) -> logging.Logger:
    """Get a logger under the `app.` namespace. Usage: `get_logger("cezih")` → `app.cezih`."""
    return logging.getLogger(f"app.{name}")


def setup_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Configure root logger with structured output. Called once at startup."""
    root = logging.getLogger()

    # Remove any handlers left by basicConfig or previous setup
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.set_name("structured")

    fmt_lower = fmt.lower().strip()
    if fmt_lower == "text":
        handler.setFormatter(TextFormatter())
    else:
        handler.setFormatter(JsonFormatter())

    root.addHandler(handler)

    # Validate + set level
    numeric = getattr(logging, level.upper(), None)
    if isinstance(numeric, int):
        root.setLevel(numeric)
    else:
        root.setLevel(logging.INFO)

    # Quiiet noisy third-party loggers
    for noisy in ("uvicorn.access", "httpx", "httpcore", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
