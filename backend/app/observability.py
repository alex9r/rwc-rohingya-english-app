"""Request IDs, structured logs and ML metrics for CloudWatch.

Learner input must never reach the logs (docs/aws-architecture.md §5.1), so
nothing here records request bodies, query strings, transcripts or translations.
Requests are logged by route template (``/api/words/{word_id}``), not raw path.

In AWS, set LOG_FORMAT=json: every line is then one JSON object, and CloudWatch
metric filters (infra/modules/monitoring) turn the ``ml_request`` lines into metrics.
"""

import contextvars
import json
import logging
import os
import re
import sys
import time
import uuid
from datetime import UTC, datetime

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

access_log = logging.getLogger("app.access")
ml_log = logging.getLogger("app.ml")

# Accept a caller's request ID only if it can't inject anything into the logs.
# API Gateway's request IDs are base64-like and may end in "=".
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._=-]{1,64}$")


def _request_id(headers: dict[bytes, bytes]) -> str:
    """X-Request-ID if safe; else API Gateway's ID from the Lambda Web Adapter; else new."""
    incoming = headers.get(b"x-request-id", b"").decode("latin-1")
    if _SAFE_REQUEST_ID.match(incoming):
        return incoming
    # On Lambda, the Web Adapter passes API Gateway's requestContext as JSON in this
    # header, so access logs and app logs share API Gateway's request ID.
    context = headers.get(b"x-amzn-request-context")
    if context:
        try:
            gateway_id = json.loads(context).get("requestId")
        except (ValueError, AttributeError):
            gateway_id = None
        if isinstance(gateway_id, str) and _SAFE_REQUEST_ID.match(gateway_id):
            return gateway_id
    return uuid.uuid4().hex


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            **getattr(record, "fields", {}),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields = " ".join(f"{k}={v}" for k, v in getattr(record, "fields", {}).items())
        line = f"{record.levelname} {record.name} [{getattr(record, 'request_id', None)}] "
        line += f"{record.getMessage()} {fields}".rstrip()
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging() -> None:
    """Send the app's loggers to stdout, as JSON when LOG_FORMAT=json."""
    logger = logging.getLogger("app")
    if getattr(logger, "_rwc_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    json_logs = os.getenv("LOG_FORMAT", "text").lower() == "json"
    handler.setFormatter(JsonFormatter() if json_logs else TextFormatter())
    logger.addHandler(handler)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    logger.propagate = False
    logger._rwc_configured = True


class RequestContextMiddleware:
    """Tags each request with an ID (echoed as X-Request-ID) and logs one access line."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id(dict(scope["headers"]))
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500

        async def send_with_id(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-request-id", request_id.encode()),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            route = scope.get("route")
            access_log.info(
                "request",
                extra={
                    "fields": {
                        "event": "request",
                        "method": scope["method"],
                        "route": getattr(route, "path", None) or "unmatched",
                        "status": status,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    }
                },
            )
            request_id_var.reset(token)


def log_ml_request(service: str, status: str, latency_ms: float) -> None:
    """One line per ML call; metric filters count these by service and status."""
    ml_log.info(
        "ml_request",
        extra={
            "fields": {
                "event": "ml_request",
                "service": service,
                "status": status,
                "latency_ms": round(latency_ms, 1),
            }
        },
    )
