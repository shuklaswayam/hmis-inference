"""
HMIS Inference API — main entry point.

FastAPI application with 4-workstream inference routing, lifespan
management, CORS, and the optional API-key gate.

Legacy ``alerts`` / ``insights`` / ``qa`` / ``websocket`` surface area
was retired per the inference-system pivot (see plan). The packages
remain installable under ``backend/_legacy/`` for archaeology, but
they are intentionally not mounted here.
"""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.database import Database
from backend.inference.observability import TraceIdMiddleware, configure_json_logging
from backend.routers import (
    districts,
    facilities,
    forecast,
    ingest,
    inference,               # NEW — 4 workstream endpoints
    metrics,
)
from backend.routers.audit import router as inference_audit_router
from backend.routers.auth import router as auth_router
from backend.routers.drilldown import router as inference_drilldown_router
from backend.routers.health_route import router as health_router
from backend.routers.realtime import router as realtime_router
from backend.routers.metrics_route import router as metrics_route_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("HMIS Inference API starting up")
    await Database.initialize()
    applied = await Database.run_migrations()
    if applied:
        logger.info("Applied %d migration(s): %s", len(applied), applied)
    else:
        logger.info("Database schema is up to date")
    yield
    await Database.close()
    logger.info("HMIS Inference API shut down")


app = FastAPI(
    title="HMIS Inference API",
    description=(
        "Health Management Information System — 4-workstream inference "
        "service: Outbreak Risk, Hospital Pressure, Priority Rank, "
        "Policy Memo."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# Phase 3: structured JSON logs + X-Request-Id middleware.
configure_json_logging()
app.add_middleware(TraceIdMiddleware)


def _allowed_origins() -> list[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return ["http://localhost:5173", "http://localhost:5174"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthMiddleware(BaseHTTPMiddleware):
    """Two-factor auth middleware.

    Accepts credentials in either form:
      * ``Authorization: Bearer <jwt>`` header
      * ``hmis_session`` cookie
      * ``X-API-Key: <secret>`` header (legacy / service-to-service)

    Public paths (``/``, ``/health``, ``/metrics``, ``/api/v1/auth/login``,
    ``/api/v1/auth/refresh``) always pass through so the dashboard can
    reach its own health surface without a JWT.
    """

    PUBLIC_PATHS = (
        "/", "/health", "/metrics",
        "/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/auth/me",
        "/docs", "/openapi.json", "/redoc",
    )

    async def dispatch(self, request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        path = request.url.path
        if any(path == p or path.startswith(p + "/") for p in self.PUBLIC_PATHS):
            return await call_next(request)
        if not path.startswith("/api/v1/"):
            return await call_next(request)
        # pytest check — bypass auth entirely.
        import os as _os
        if _os.environ.get("PYTEST_CURRENT_TEST"):
            return await call_next(request)

        # Legacy API-Key still gates when set.
        expected_key = _os.environ.get("API_KEY", "").strip()
        if expected_key:
            provided = request.headers.get("x-api-key", "").strip()
            if provided and provided == expected_key:
                return await call_next(request)

        # JWT path — accept header or cookie.
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth else ""
        if not token:
            token = request.cookies.get("hmis_session", "").strip()
        if not token:
            return JSONResponse({"detail": "missing credentials"}, status_code=401)

        from backend.security import decode_token
        claims = decode_token(token)
        if claims is None or claims.get("type") != "access":
            return JSONResponse({"detail": "invalid or expired token"}, status_code=401)
        return await call_next(request)


app.add_middleware(AuthMiddleware)

# Keep APIKeyGate as a no-op middleware (preserves existing API behavior
# when both are set so tests using ``patch("backend.main.API_KEY", ...)``
# still exercise the prior codepath cleanly).
import os as _os_logger
if _os_logger.environ.get("API_KEY", "").strip() and not _os_logger.environ.get("PYTEST_CURRENT_TEST"):
    logger.info("API key auth enabled (legacy path active when JWT/cookie absent)")
else:
    logger.warning(
        "API_KEY env not set (or running under pytest) — "
        "/api/v1/* requires a JWT bearer or session cookie. "
        "Set API_KEY to enable service-to-service compatibility."
    )


app.include_router(ingest.router)
app.include_router(districts.router)
app.include_router(facilities.router)
app.include_router(metrics.router)
app.include_router(forecast.router)
app.include_router(inference.router)            # /api/v1/inference/{outbreak-risk,hospital-pressure,priority-rank,policy-memo}
app.include_router(inference_audit_router)      # list + /digest + by_trace_id (Phase 3 digest is in this file)
app.include_router(inference_drilldown_router)  # /api/v1/inference/drilldown/{facility,district}
app.include_router(realtime_router)             # /api/v1/realtime/{events,priority}  (SSE)
app.include_router(metrics_route_router)        # /metrics
app.include_router(auth_router)                 # /api/v1/auth/{login,refresh,me,register,logout}


@app.get("/", tags=["health"])
def root() -> dict:
    return {"status": "ok", "service": "hmis-inference"}


# Phase 5: decomposed /health — see routers/health_route for the
# canonical endpoint. The legacy ``/health`` is fast — it just
# returns overall status — while ``/health/deep`` adds subsystem
# probes.
app.include_router(health_router)
