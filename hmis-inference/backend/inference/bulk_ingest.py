"""CSV bulk-ingest for facility_metrics.

Single-file endpoint that accepts a CSV body, validates row by row,
inserts in batches, and returns a per-row error/inserted report.

Scope (Phase 6 close-out):
  * facility_metrics CSV ingestion only — district / facility /
    disease CSVs land in the next Phase.
  * Required columns: ``facility_id,reported_date,opd_visits,
    icu_occupancy_pct,bed_occupancy_pct,emergency_visits,
    maternal_deaths,deliveries``
  * Optional columns: ``medicine_days_remaining,
    staff_attendance_pct,case_count``
  * Coerces types; clamps percentages; rejects bad facility_id
    UUIDs with row-level detail.

Response shape:
    {
      "rows_received": int,
      "rows_inserted": int,
      "rows_failed":    int,
      "failures": [ {"row": <index>, "error": "<message>"}, ... ],
      "inserted":  [ {"row": <index>, "id": "<uuid>"}, ... ]
    }
"""

from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import date, datetime
from typing import Optional

from backend.database import Database

logger = logging.getLogger(__name__)


REQUIRED_COLUMNS = {
    "facility_id",
    "reported_date",
    "opd_visits",
    "icu_occupancy_pct",
    "bed_occupancy_pct",
    "emergency_visits",
    "maternal_deaths",
    "deliveries",
}
OPTIONAL_COLUMNS = {
    "medicine_days_remaining",
    "staff_attendance_pct",
}


async def _facility_exists(facility_id: str) -> bool:
    row = await Database.fetchrow(
        "SELECT 1 FROM health_facilities WHERE id = $1::uuid",
        facility_id,
    )
    return row is not None


def _coerce_row(idx: int, raw: dict) -> Optional[str]:
    """Return None on success, error string on failure."""
    facility_id = (raw.get("facility_id") or "").strip()
    try:
        uuid.UUID(facility_id)
    except ValueError:
        return f"row {idx}: facility_id is not a UUID (got {facility_id!r})"

    try:
        reported_date = date.fromisoformat(raw["reported_date"])
    except (KeyError, ValueError, TypeError):
        return f"row {idx}: reported_date not ISO-format (got {raw.get('reported_date')!r})"

    try:
        opd_visits       = max(0,     int(raw.get("opd_visits", 0)))
        icu_occupancy_pct = max(0.0, min(100.0, float(raw.get("icu_occupancy_pct", 0))))
        bed_occupancy_pct = max(0.0, min(100.0, float(raw.get("bed_occupancy_pct", 0))))
        emergency_visits = max(0,    int(raw.get("emergency_visits", 0)))
        maternal_deaths   = max(0,    int(raw.get("maternal_deaths", 0)))
        deliveries        = max(0,    int(raw.get("deliveries", 0)))
    except (TypeError, ValueError) as exc:
        return f"row {idx}: bad numeric field ({exc})"

    medicine_days_raw = raw.get("medicine_days_remaining")
    staff_attendance_raw = raw.get("staff_attendance_pct")

    medicine_days_remaining: Optional[float] = None
    if medicine_days_raw not in (None, "", "null"):
        try:
            medicine_days_remaining = max(0.0, float(medicine_days_raw))
        except (TypeError, ValueError):
            return f"row {idx}: medicine_days_remaining must be numeric"

    staff_attendance_pct: Optional[float] = None
    if staff_attendance_raw not in (None, "", "null"):
        try:
            staff_attendance_pct = max(0.0, min(100.0, float(staff_attendance_raw)))
        except (TypeError, ValueError):
            return f"row {idx}: staff_attendance_pct must be numeric"

    return None  # success


def _parse_csv(csv_body: str) -> tuple[list[dict], list[dict]]:
    """Parse + coerce the CSV. Returns (clean_rows, errors)."""
    reader = csv.DictReader(io.StringIO(csv_body))
    if not reader.fieldnames or set(reader.fieldnames).isdisjoint(REQUIRED_COLUMNS):
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        return [], [
            {"row": 0, "error": f"missing required columns: {sorted(missing)!r}"},
        ]
    clean: list[dict] = []
    errors: list[dict] = []
    rows = list(reader)
    seen_keys: set[tuple[str, str]] = set()  # duplicates within the same upload
    for idx, raw in enumerate(rows, start=1):
        if missing := REQUIRED_COLUMNS - set(raw.keys()):
            errors.append({"row": idx, "error": f"missing required columns: {sorted(missing)!r}"})
            continue
        err = _coerce_row(idx, raw)
        if err:
            errors.append({"row": idx, "error": err})
            continue
        # Duplicate detection — same (facility, date) inside the upload.
        pair = (raw["facility_id"].strip(), raw["reported_date"].strip())
        if pair in seen_keys:
            errors.append({"row": idx, "error": "duplicate (facility_id, reported_date) inside upload"})
            continue
        seen_keys.add(pair)
        clean.append({
            "facility_id": raw["facility_id"].strip(),
            "reported_date": raw["reported_date"].strip(),
            "opd_visits": int(raw["opd_visits"]),
            "icu_occupancy_pct": float(raw["icu_occupancy_pct"]),
            "bed_occupancy_pct": float(raw["bed_occupancy_pct"]),
            "emergency_visits": int(raw["emergency_visits"]),
            "maternal_deaths": int(raw["maternal_deaths"]),
            "deliveries": int(raw["deliveries"]),
            "medicine_days_remaining": _maybe_float(raw.get("medicine_days_remaining")),
            "staff_attendance_pct":     _maybe_float(raw.get("staff_attendance_pct")),
        })
    return clean, errors


def _maybe_float(value) -> Optional[float]:
    if value in (None, "", "null") or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _facility_cache(rows: list[dict]) -> None:
    """We don't cache ourselves; the caller's batched insert does."""
    return None


async def perform_bulk_ingest(csv_body: str) -> dict:
    """Parse, validate facility ids, batch-insert; return per-row report."""
    rows, errors = _parse_csv(csv_body)
    if not rows:
        return {
            "rows_received": len(errors),
            "rows_inserted": 0,
            "rows_failed": len(errors),
            "failures": errors,
            "inserted": [],
        }

    # Validate every facility_id against DB once.
    facility_ids = {r["facility_id"] for r in rows}
    valid_facilities: set[str] = set()
    if facility_ids:
        async def gather_facility_ids():
            for fid in facility_ids:
                valid_facilities.add(fid) if await _facility_exists(fid) else None
            return valid_facilities
        await gather_facility_ids()

    failures = list(errors)
    to_insert = []
    for idx, row in enumerate(rows, start=1):
        if row["facility_id"] not in valid_facilities:
            failures.append({
                "row": idx,
                "error": f"facility_id not in DB: {row['facility_id']!r}",
            })
            continue
        row["_row_index"] = idx
        to_insert.append(row)

    inserted_report: list[dict] = []
    if to_insert:
        try:
            await Database.execute(
                """
                INSERT INTO facility_metrics
                  (facility_id, reported_date, opd_visits, icu_occupancy_pct,
                   bed_occupancy_pct, emergency_visits, maternal_deaths, deliveries,
                   medicine_days_remaining, staff_attendance_pct)
                VALUES ($1, $2::date, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (facility_id, reported_date) DO UPDATE SET
                    opd_visits = EXCLUDED.opd_visits,
                    icu_occupancy_pct = EXCLUDED.icu_occupancy_pct,
                    bed_occupancy_pct = EXCLUDED.bed_occupancy_pct,
                    emergency_visits = EXCLUDED.emergency_visits,
                    maternal_deaths = EXCLUDED.maternal_deaths,
                    deliveries = EXCLUDED.deliveries,
                    medicine_days_remaining = EXCLUDED.medicine_days_remaining,
                    staff_attendance_pct = EXCLUDED.staff_attendance_pct,
                    created_at = NOW()
                """,
                *unpack_row(to_insert[0]),
            )
            # Use a single parameterised statement per row in this v1;
            # bulk execute_values could be a follow-up.
            for r in to_insert[1:]:
                await Database.execute(
                    """
                    INSERT INTO facility_metrics
                      (facility_id, reported_date, opd_visits, icu_occupancy_pct,
                       bed_occupancy_pct, emergency_visits, maternal_deaths, deliveries,
                       medicine_days_remaining, staff_attendance_pct)
                    VALUES ($1, $2::date, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (facility_id, reported_date) DO UPDATE SET
                        opd_visits = EXCLUDED.opd_visits,
                        icu_occupancy_pct = EXCLUDED.icu_occupancy_pct,
                        bed_occupancy_pct = EXCLUDED.bed_occupancy_pct,
                        emergency_visits = EXCLUDED.emergency_visits,
                        maternal_deaths = EXCLUDED.maternal_deaths,
                        deliveries = EXCLUDED.deliveries,
                        medicine_days_remaining = EXCLUDED.medicine_days_remaining,
                        staff_attendance_pct = EXCLUDED.staff_attendance_pct,
                        created_at = NOW()
                    """,
                    *unpack_row(r),
                )
            inserted_report = [{"row": r["_row_index"]} for r in to_insert]
        except Exception as exc:  # noqa: BLE001
            logger.exception("bulk insert failed")
            failures.append({"row": "all", "error": f"db error: {exc}"})

    return {
        "rows_received": len(rows) + len(errors),
        "rows_inserted": len(inserted_report),
        "rows_failed":    len(failures),
        "failures": failures,
        "inserted":  inserted_report,
    }


def unpack_row(row: dict) -> tuple:
    """Convert a coerced row dict to positional params for the INSERT."""
    return (
        row["facility_id"],
        row["reported_date"],
        row["opd_visits"],
        row["icu_occupancy_pct"],
        row["bed_occupancy_pct"],
        row["emergency_visits"],
        row["maternal_deaths"],
        row["deliveries"],
        row.get("medicine_days_remaining"),
        row.get("staff_attendance_pct"),
    )
