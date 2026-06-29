"""Lightweight ``/metrics`` endpoint emitting Prometheus-style text."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from backend.inference import metrics

router = APIRouter(tags=["observability"])


@router.get("/metrics", summary="Prometheus-style metrics for inference")
async def get_metrics():
    return PlainTextResponse(
        metrics.to_prometheus_text(),
        media_type="text/plain; version=0.0.4",
    )


@router.get("/metrics/internal", summary="Internal snapshot (Phase 5)")
async def snapshot():
    """JSON snapshot that's easier to consume from CI than text.

    Not the canonical scrape surface (use /metrics), but a cheap helper
    for ad-hoc diagnostics.
    """
    return {
        "ok": True,
        "metrics_lines": metrics.to_prometheus_text().count("\n"),
    }
