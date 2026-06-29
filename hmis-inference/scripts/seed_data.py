#!/usr/bin/env python3
"""
Seed script for HMIS Inference System.

Inserts 5 districts and 256 procedurally-generated health facilities
(~55 per district on average) into PostgreSQL. Facility IDs are
deterministic via ``uuid.uuid5`` so re-runs are idempotent.

Distribution totals exactly 256 facilities across the districts
(Ahmedabad 60 / Surat 55 / Vadodara 50 / Rajkot 50 / Bhavnagar 41),
matching the scope called out for Hospital Pressure Classification.
"""

import os
import random
import subprocess
import sys
import urllib.parse
import uuid
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://hmis:hmis_password@localhost:5432/hmis"
)
parsed = urllib.parse.urlparse(DATABASE_URL)
DB_CONFIG = {
    "host": parsed.hostname or "localhost",
    "port": parsed.port or 5432,
    "database": parsed.path.lstrip("/") or "hmis",
    "user": parsed.username or "hmis",
    "password": parsed.password or "hmis_password",
}

# Random-but-deterministic namespace so derived UUIDs stay stable
# across runs/machines. Stable seed namespace kept verbatim from
# prior versions to preserve back-compat where it matters.
NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

DISTRICTS = [
    {"name": "Ahmedabad", "state": "Gujarat", "population": 8059441, "zone": "Central"},
    {"name": "Bhavnagar", "state": "Gujarat", "population": 2880365, "zone": "Saurashtra"},
    {"name": "Rajkot",    "state": "Gujarat", "population": 3804558, "zone": "Saurashtra"},
    {"name": "Surat",     "state": "Gujarat", "population": 6081322, "zone": "South"},
    {"name": "Vadodara",  "state": "Gujarat", "population": 4165626, "zone": "Central"},
]

# District centroids used to scatter lat/lng with bounded jitter.
DISTRICT_CENTROIDS = {
    "Ahmedabad": (23.0225, 72.5714),
    "Bhavnagar": (21.7645, 72.1519),
    "Rajkot":    (22.3039, 70.8022),
    "Surat":     (21.1902, 72.8311),
    "Vadodara":  (22.3072, 73.1812),
}

# Facility mix: type, display name, beds_total, icu_beds.
# Reasonable for Gujarat public-health sites.
FACILITY_TYPES = [
    ("PHC",                     "PHC",                       6,    0),
    ("CHC",                     "CHC",                      30,    4),
    ("Sub-District Hospital",   "Sub-District Hospital",   100,   10),
    ("Urban Health Center",     "Urban Health Center",      12,    0),
    ("Trust Hospital",          "Trust Hospital",           80,    8),
    ("General Hospital",        "General Hospital",        200,   15),
    ("District Hospital",       "District Hospital",       500,   30),
    ("Medical College Hospital", "Medical College Hospital", 1000, 60),
]

# Per-district counts of each facility type. Totals must sum to 256
# (60 + 55 + 50 + 50 + 41). Order is preserved within each district so
# larger facilities come last in the generated roster.
DISTRICT_FACILITY_TARGETS = {
    "Ahmedabad": {"PHC": 18, "CHC": 11, "Sub-District Hospital": 9, "Urban Health Center": 5,
                  "Trust Hospital": 5, "General Hospital": 6, "District Hospital": 3, "Medical College Hospital": 3},
    "Bhavnagar": {"PHC": 12, "CHC": 8,  "Sub-District Hospital": 7, "Urban Health Center": 4,
                  "Trust Hospital": 3, "General Hospital": 4, "District Hospital": 2, "Medical College Hospital": 1},
    "Rajkot":    {"PHC": 14, "CHC": 10, "Sub-District Hospital": 8, "Urban Health Center": 5,
                  "Trust Hospital": 4, "General Hospital": 5, "District Hospital": 2, "Medical College Hospital": 2},
    "Surat":     {"PHC": 16, "CHC": 10, "Sub-District Hospital": 9, "Urban Health Center": 5,
                  "Trust Hospital": 4, "General Hospital": 6, "District Hospital": 3, "Medical College Hospital": 2},
    "Vadodara":  {"PHC": 14, "CHC": 10, "Sub-District Hospital": 8, "Urban Health Center": 4,
                  "Trust Hospital": 4, "General Hospital": 6, "District Hospital": 2, "Medical College Hospital": 2},
}


def _facility_district_total(targets: dict[str, dict[str, int]]) -> int:
    return sum(counts.values() for counts in targets.values())


def _facility_total(totals: dict[str, int]) -> int:
    return sum(totals.values())


def _assert_totals_match_256() -> None:
    totals = {d: _facility_district_total(t) for d, t in DISTRICT_FACILITY_TARGETS.items()}
    grand = _facility_total(totals)
    if grand != 256:
        raise RuntimeError(
            f"DISTRICT_FACILITY_TARGETS must total 256 facilities; got {grand} ({totals})"
        )


def _make_facility_id(district_name: str, short_type: str, idx: int) -> uuid.UUID:
    """Deterministic UUIDv5 — same key gives the same id on every run."""
    return uuid.uuid5(NAMESPACE, f"hmis.facility.{district_name}.{short_type}.{idx:04d}")


def _jitter_latlng(centroid: tuple[float, float], district_name: str, idx: int) -> tuple[float, float]:
    """Hash-based jitter so layouts stay reproducible across runs."""
    rng = random.Random(f"{district_name}-{idx}")
    # Confinement to ~0.06 deg (~6.5 km) keeps each facility inside
    # its district's rough footprint without crossing the next one.
    dlat = rng.uniform(-0.06, 0.06)
    dlng = rng.uniform(-0.06, 0.06)
    return (round(centroid[0] + dlat, 6), round(centroid[1] + dlng, 6))


def generate_facilities() -> list[dict]:
    """Procedurally generate 256 facilities across all districts."""
    _assert_totals_match_256()
    out: list[dict] = []
    # Iterate by type order so small facilities get stable early slots.
    type_order = [(short, full, beds, icu) for (short, full, beds, icu) in FACILITY_TYPES]
    for district_name, targets in DISTRICT_FACILITY_TARGETS.items():
        centroid = DISTRICT_CENTROIDS[district_name]
        per_type_idx = {short: 0 for short, *_ in type_order}
        for row_idx, (short, full, beds, icu) in enumerate(type_order):
            count = targets.get(short, 0)
            for _ in range(count):
                idx = per_type_idx[short]
                per_type_idx[short] += 1
                facility_id = _make_facility_id(district_name, short, idx)
                lat, lng = _jitter_latlng(centroid, district_name, row_idx * 1000 + idx)
                out.append(
                    {
                        "id": facility_id,
                        "name": f"{full} {district_name}-{idx:03d}",
                        "facility_type": full,
                        "beds_total": beds,
                        "icu_beds": icu,
                        "latitude": lat,
                        "longitude": lng,
                        "_district_name": district_name,
                    }
                )
    return out


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def seed_districts(conn) -> dict[str, str]:
    district_ids: dict[str, str] = {}
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        for d in DISTRICTS:
            cur.execute(
                """
                INSERT INTO districts (name, state, population, zone)
                VALUES (%(name)s, %(state)s, %(population)s, %(zone)s)
                ON CONFLICT (name) DO UPDATE SET state = EXCLUDED.state
                RETURNING id
                """,
                d,
            )
            row = cur.fetchone()
            assert row is not None, "INSERT...RETURNING always returns id"
            district_ids[d["name"]] = row["id"]
    conn.commit()
    return district_ids


def seed_facilities(conn, facilities: list[dict], district_ids: dict[str, str]) -> int:
    inserted = 0
    with conn.cursor() as cur:
        for f in facilities:
            cur.execute(
                """
                INSERT INTO health_facilities (
                    id, district_id, name, facility_type, beds_total,
                    icu_beds, latitude, longitude
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    str(f["id"]),
                    district_ids[f["_district_name"]],
                    f["name"],
                    f["facility_type"],
                    f["beds_total"],
                    f["icu_beds"],
                    f["latitude"],
                    f["longitude"],
                ),
            )
            inserted += cur.rowcount
    conn.commit()
    return inserted


def verify_counts(conn) -> dict:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT COUNT(*) AS n FROM districts")
        districts_count = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM health_facilities")
        facilities_count = cur.fetchone()["n"]
        cur.execute(
            """
            SELECT d.name, COUNT(hf.id) AS n
            FROM districts d
            LEFT JOIN health_facilities hf ON hf.district_id = d.id
            GROUP BY d.name
            ORDER BY d.name
            """
        )
        per_district = cur.fetchall()
    return {
        "districts": districts_count,
        "facilities": facilities_count,
        "per_district": per_district,
    }


def train_outbreak_classifier() -> bool:
    """Fit Workstream 1's decision tree from the freshly-seeded data.

    Best-effort: never raise out of main() — seed success is what the
    operator is waiting for. The model can always be retrained later
    via ``python scripts/train_outbreak_classifier.py``.
    """
    train_script = Path(__file__).resolve().parent / "train_outbreak_classifier.py"
    if not train_script.exists():
        print(f"  Skipping — training script missing at {train_script}.")
        return False
    print(f"  Invoking: {sys.executable} {train_script.name}")
    result = subprocess.run(
        [sys.executable, str(train_script)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"  Training failed (exit {result.returncode}).")
        for line in result.stderr.splitlines():
            print(f"    [stderr] {line}")
        print("  Re-run later: python scripts/train_outbreak_classifier.py")
        return False
    for line in result.stdout.splitlines():
        if line.strip():
            print(f"    {line}")
    return True


def main() -> None:
    print("Connecting to database…")
    conn = get_connection()
    try:
        print("Seeding districts…")
        district_ids = seed_districts(conn)
        print(f"  Districts ready: {sorted(district_ids.keys())}")

        print("\nGenerating 256 facilities procedurally…")
        facilities = generate_facilities()
        # Sanity: 256 by design — checked again at insert-time.
        assert len(facilities) == 256, f"expected 256 facilities, got {len(facilities)}"

        print("Inserting facilities (idempotent via uuid5 PK)…")
        inserted = seed_facilities(conn, facilities, district_ids)
        print(f"  Inserted {inserted} new facilities (rest already existed)")

        counts = verify_counts(conn)
        print("\n=== Verification ===")
        print(f"Total districts:  {counts['districts']}")
        print(f"Total facilities: {counts['facilities']}")
        print("Facilities per district:")
        for row in counts["per_district"]:
            print(f"  {row['name']}: {row['n']}")
        if counts["facilities"] != 256:
            print(
                f"\nNOTE: configured for 256; DB has {counts['facilities']} "
                "(re-run is safe — uuid5 IDs make inserts no-op)."
            )

        print("\nTraining Outbreak Risk Classifier (Workstream 1)…")
        train_outbreak_classifier()

    finally:
        conn.close()
        print("\nDone!")


if __name__ == "__main__":
    main()
