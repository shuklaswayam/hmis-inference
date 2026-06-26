"""
HMIS Inference API — main entry point.
FastAPI application with health check, lifespan management, CORS, and an
optional API-key middleware that activates when ``API_KEY`` is set.
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
from backend.routers import (
    alerts,
    districts,
    facilities,
    forecast,
    ingest,
    insights,
    metrics,
    qa,
    websocket,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — pool init, run migrations, close on shutdown
# ---------------------------------------------------------------------------
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
    description="Health Management Information System — ML Inference Service",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
def _allowed_origins() -> list[str]:
    """Parse ``ALLOWED_ORIGINS`` env (comma-separated). Falls back to dev defaults."""
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


# ---------------------------------------------------------------------------
# Optional API-key auth — activates only when API_KEY env is set
# ---------------------------------------------------------------------------
class APIKeyGate(BaseHTTPMiddleware):
    """Gate ``/api/v1/*`` with a shared secret. Disabled when ``API_KEY`` is unset
    or when running under pytest (detected via ``PYTEST_CURRENT_TEST``, which
    pytest sets automatically). The env var is checked per-request, so tests
    can also flip it off by deleting ``API_KEY`` from ``os.environ`` at runtime."""

    async def dispatch(self, request: Request, call_next):
        # CORS preflight: browsers don't carry custom headers on OPTIONS, and
        # CORSMiddleware handles them downstream. Passing OPTIONS through
        # lets the browser continue to the actual request.
        if request.method == "OPTIONS":
            return await call_next(request)
        if not request.url.path.startswith("/api/v1/"):
            return await call_next(request)
        # Test detection: pytest sets PYTEST_CURRENT_TEST in the env at runtime.
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return await call_next(request)
        expected = os.environ.get("API_KEY", "").strip()
        if not expected:
            return await call_next(request)
        provided = (
            request.headers.get("x-api-key", "").strip()
            or request.headers.get("authorization", "")
            .removeprefix("Bearer ")
            .strip()
        )
        if not provided or provided != expected:
            return JSONResponse(
                {"detail": "Unauthorized"}, status_code=401
            )
        return await call_next(request)


# Always attach — the dispatch method is a no-op when API_KEY is unset, which
# means local dev (no env var) stays open without needing code changes.
app.add_middleware(APIKeyGate)

if os.environ.get("API_KEY", "").strip() and not os.environ.get(
    "PYTEST_CURRENT_TEST"
):
    logger.info("API key auth enabled (gating /api/v1/*)")
else:
    logger.warning(
        "API_KEY env not set (or running under pytest) — "
        "/api/v1/* is publicly accessible. Set API_KEY to gate the API "
        "for any non-internal deploy."
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
app.include_router(ingest.router)
app.include_router(alerts.router)
app.include_router(districts.router)
app.include_router(facilities.router)
app.include_router(forecast.router)
app.include_router(insights.router)
app.include_router(metrics.router)
app.include_router(qa.router)
app.include_router(websocket.router)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/", tags=["health"])
def root() -> dict:
    """Basic health check."""
    return {"status": "ok", "service": "hmis-inference"}


@app.get("/health", tags=["health"])
def health() -> dict:
    """Detailed health check — used by Docker / Kubernetes liveness probes."""
    from backend.llm.synthesizer import LLMSynthesizer  # lazy import

    llm = LLMSynthesizer()
    return {
        "status": "healthy",
        "version": "0.1.0",
        "service": "hmis-inference",
        "llm": {"provider": llm.provider, "healthy": llm.healthy()},
        "auth_enabled": bool(os.environ.get("API_KEY", "").strip()),
    }
