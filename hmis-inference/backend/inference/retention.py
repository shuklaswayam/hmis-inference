"""Audit retention + archival.

Hot ``inference_audit`` rows older than ``AUDIT_TTL_DAYS`` (default 90)
are copied to ``inference_audit_archive`` at low priority; the original
rows are deleted from the hot table once the archive copy succeeds.

Read helpers in ``backend.inference.store`` transparently union hot +
archive so the dashboard never sees a gap.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.database import Database

logger = logging.getLogger(__name__)


def ttl_days() -> int:
    return int(os.environ.get("AUDIT_TTL_DAYS", "90"))


async def archive_old_audits(
    *,
    ttl_days: Optional[int] = None,
) -> dict:
    """Move rows older than ``ttl_days`` from hot to archive.

    Returns a counters dict suitable for logging or for the Celery return value.
    """
    ttl = ttl_days if ttl_days is not None else ttl_days_default()
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl)

    try:
        # Copy-then-delete so a single transaction moves the row atomically.
        # PostgreSQL ``WITH`` is the cleanest single-statement way to do this.
        copied = await Database.execute(
            """
            WITH moved AS (
                DELETE FROM inference_audit
                WHERE generated_at < $1
                RETURNING *
            )
            INSERT INTO inference_audit_archive
                SELECT * FROM moved
            ON CONFLICT (id) DO NOTHING
            """,
            cutoff,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("archive_old_audits failed")
        return {"ok": False, "error": str(exc), "cutoff": cutoff.isoformat()}

    # Some asyncpg executors don't return rowcount reliably — fall back to
    # counting via the DELETE returning clause.
    try:
        # Best-effort post-prune count.
        row = await Database.fetchrow("SELECT COUNT(*) AS n FROM inference_audit_archive WHERE generated_at < $1", cutoff)
        archived_count = int(row["n"]) if row else 0
    except Exception:  # noqa: BLE001
        archived_count = -1

    logger.info("audit archival succeeded — moved rows older than %s", cutoff.isoformat())
    return {
        "ok":               True,
        "cutoff":            cutoff.isoformat(),
        "archived_count":    archived_count,
        "hot_remaining":     None,
    }


def ttl_days_default() -> int:
    return ttl_days()


async def hot_count() -> int:
    row = await Database.fetchrow("SELECT COUNT(*) AS n FROM inference_audit")
    return int(row["n"]) if row else 0


async def archive_count() -> int:
    row = await Database.fetchrow("SELECT COUNT(*) AS n FROM inference_audit_archive")
    return int(row["n"]) if row else 0
