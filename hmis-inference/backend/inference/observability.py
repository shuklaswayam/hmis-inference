"""Structured logging — JSON formatter + context-bound trace_id hook.

A small ``TraceIdMiddleware`` attaches the request's ``X-Request-Id`` to
the logger adapter so every log line emitted inside the request handler
carries the id. Falls back to generating a uuid4 when the header is
missing.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_trace_id_ctx: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


def current_trace_id() -> Optional[str]:
    return _trace_id_ctx.get()


def set_trace_id(value: Optional[str]) -> None:
    _trace_id_ctx.set(value)


class JsonFormatter(logging.Formatter):
    """Compact JSON formatter that always carries the trace_id when available."""

    def format(self, record: logging.LogRecord) -> str:
        import json
        body = {
            "ts":       self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level":    record.levelname,
            "logger":   record.name,
            "message":  record.getMessage(),
        }
        tid = current_trace_id()
        if tid:
            body["trace_id"] = tid
        # Promote common ``exc_info`` to text.
        if record.exc_info:
            body["exception"] = self.formatException(record.exc_info)
        # Allow custom extra={...} payload — flatten keys.
        for key in ("event", "workstream", "severity", "facility_id", "district_id"):
            value = getattr(record, key, None)
            if value is not None:
                body[key] = value
        return json.dumps(body, default=str, ensure_ascii=False)


def configure_json_logging(level: int = logging.INFO) -> None:
    """Swap the root logger's formatting to JSON. Idempotent."""
    root = logging.getLogger()
    # Strip existing formatters so reconfiguration has effect.
    for h in list(root.handlers):
        h.setFormatter(JsonFormatter())
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)
    root.setLevel(level)


class TraceIdMiddleware(BaseHTTPMiddleware):
    """Reads (or generates) the request's trace id, attaches it to the
    logging context, and echoes it on the response header."""

    HEADER = "X-Request-Id"

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get(self.HEADER)
        trace_id = incoming if incoming else str(uuid.uuid4())
        token = _trace_id_ctx.set(trace_id)
        try:
            response: Response = await call_next(request)
        finally:
            _trace_id_ctx.reset(token)
        response.headers[self.HEADER] = trace_id
        return response
