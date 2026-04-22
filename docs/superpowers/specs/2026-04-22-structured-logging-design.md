# Structured Logging for Operational Debugging

**Date:** 2026-04-22
**Status:** Approved
**Scope:** Backend structured logs + correlation IDs + client error relay
**Budget:** Zero — self-hosted, no external services
**Goal:** When something breaks in prod, find the root cause quickly via SSH + jq

## Problem

- Backend logs are plain text — hard to parse, filter, or correlate across services
- No correlation IDs — can't trace a request from browser through backend to CEZIH
- No env-var log level control — need code change to enable DEBUG
- Frontend errors are invisible — browser console only
- Docker logs had no rotation (250M Caddy log on 85% full disk — **fixed in 34c98dd**)

## Architecture

```
Browser error → POST /api/client-log → Backend structured log → Docker stdout (rotated)
                                         ↑
Request → Middleware generates X-Request-ID → ContextVar → All loggers include it
```

## Components

### 1. JSON Log Formatter

Replace `logging.basicConfig()` in `backend/app/main.py` with a structured JSON formatter.

**Log line format:**
```json
{
  "ts": "2026-04-22T14:32:01.234Z",
  "level": "ERROR",
  "logger": "app.cezih",
  "request_id": "a1b2c3d4",
  "tenant_id": "uuid-here",
  "user_id": "uuid-here",
  "message": "CEZIH ITI-65 failed",
  "error": "ConnectionRefused",
  "status_code": 502,
  "duration_ms": 1234
}
```

- All fields optional except `ts`, `level`, `logger`, `message`
- `request_id`, `tenant_id`, `user_id` injected from ContextVar when available
- Extra fields passed via `logger.info("msg", extra={"key": "value"})`

**Env vars:**
- `LOG_LEVEL` — default `INFO`, accepts DEBUG/INFO/WARNING/ERROR/CRITICAL
- `LOG_FORMAT` — `json` (prod default) or `text` (local dev readability)

**Implementation:** Single `JsonFormatter` class in `backend/app/core/logging.py`.

### 2. Request ID Middleware

New ASGI middleware in `backend/app/middleware/request_id.py`.

**Behavior:**
- Generate UUID4 per incoming request
- Set as `X-Request-ID` response header
- Store in `ContextVar[str]` — accessible from any logger in the request scope
- Accept forwarded `X-Request-ID` header (for future load balancer/proxy chaining)
- Add to existing `request_logger.py` output

### 3. Client Error Relay

New endpoint `POST /api/client-log` in `backend/app/api/client_log.py`.

**Request schema:**
```json
{
  "message": "Uncaught TypeError: Cannot read properties of undefined",
  "stack": "TypeError: Cannot read...\n  at Component (app.js:123:45)",
  "url": "/dashboard/pacijenti/123",
  "userAgent": "Mozilla/5.0...",
  "request_id": "a1b2c3d4"
}
```

**Constraints:**
- No auth required (errors may happen before auth or in auth itself)
- Rate-limited: 5 requests per IP per minute (in-memory sliding window)
- Logged at WARNING level under `app.client_errors` logger
- `request_id` forwarded if client has it from response header

**Frontend integration:** Add error handler in `frontend/src/lib/api-client.ts` that catches unhandled errors and POSTs to `/api/client-log`.

### 4. Log Level Control

**Config changes in `backend/app/config.py`:**
```python
LOG_LEVEL: str = "INFO"
LOG_FORMAT: str = "json"
```

**docker-compose.yml** already has `env_file: .env` for backend — just add vars to `.env`.

### 5. Request Logger Enhancement

Update `backend/app/middleware/request_logger.py` to output structured JSON and include `request_id`, `tenant_id`, `user_id`, `duration_ms`, `status_code`.

## Querying Logs (SSH)

```bash
# All logs for a specific request
ssh root@server "docker logs backend | jq 'select(.request_id==\"abc-123\")'"

# All errors in the last hour
ssh root@server "docker logs backend --since 1h | jq 'select(.level==\"ERROR\")'"

# CEZIH-related failures
ssh root@server "docker logs backend | jq 'select(.logger | startswith(\"app.cezih\"))'"

# Time-range query
ssh root@server "docker logs backend | jq 'select(.ts > \"2026-04-22T14:00\" and .ts < \"2026-04-22T15:00\")'"

# Client errors only
ssh root@server "docker logs backend | jq 'select(.logger==\"app.client_errors\")'"
```

## Files Changed

| File | Change |
|------|--------|
| `backend/app/core/logging.py` | NEW — JsonFormatter, ContextVar setup, `setup_logging()` |
| `backend/app/middleware/request_id.py` | NEW — RequestID middleware |
| `backend/app/api/client_log.py` | NEW — POST /api/client-log endpoint |
| `backend/app/main.py` | Replace `basicConfig` with `setup_logging()`, add RequestID middleware |
| `backend/app/config.py` | Add LOG_LEVEL, LOG_FORMAT settings |
| `backend/app/middleware/request_logger.py` | Rewrite to structured output |
| `backend/app/api/router.py` | Mount client_log router |
| `frontend/src/lib/api-client.ts` | Add client error reporting |
| `frontend/src/app/global-error.tsx` | Wire up error boundary to reporter |
| `docker-compose.yml` | Already done — log rotation + LOG_LEVEL in env |
| `.env.example` | Add LOG_LEVEL, LOG_FORMAT documentation |

## Deferred (Not In Scope)

- Loki/Grafana — JSON format is compatible, can add later without changes
- Sentry or any external error tracking service
- Audit log search UI or export
- Log archival / retention policy / compliance preservation
- Alerting or SLO monitoring
- Distributed tracing (OpenTelemetry)

## Done Already

- Docker log rotation (34c98dd) — all services capped, Caddy was at 250M
- PostgreSQL slow query logging — `log_min_duration_statement=500ms` (34c98dd)
