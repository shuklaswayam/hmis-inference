#!/usr/bin/env python3
"""Train the Outbreak Risk Classifier (Workstream 1).

Pulls ``disease_reports`` from the database, computes per-(district,
disease) features (14-day case count, 30-day baseline ratio, deaths,
weekly slope, district z-score), labels tiers using the deterministic
rule thresholds, and fits a small scikit-learn DecisionTree. Persists
the model to ``models/outbreak_classifier.pkl`` so the inference
server can ``OutbreakClassifier().load()`` it on boot.

Usage:
    python scripts/train_outbreak_classifier.py
"""
from __future__ import annotations

import os
import statistics
import sys
import urllib.parse
from collections import defaultdict
from pathlib import Path

import psycopg2

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://hmis:hmis_password@localhost:5432/hmis"
)
_parsed = urllib.parse.urlparse(DATABASE_URL)
DB_CONFIG = {
    "host": _parsed.hostname or "localhost",
    "port": _parsed.port or 5432,
    "database": (_parsed.path or "/hmis").lstrip("/") or "hmis",
    "user": _parsed.username or "hmis",
    "password": _parsed.password or "hmis_password",
}


def fetch_disease_reports(conn) -> list[dict]:
    """Pull the last 180 days of disease reports — enough headroom for
    the worst 14-day rolling window + 30-day prior baseline."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                d.name        AS district_name,
                dr.disease_name,
                dr.reported_date,
                dr.case_count,
                dr.deaths
            FROM disease_reports dr
            JOIN health_facilities hf ON hf.id = dr.facility_id
            JOIN districts         d  ON d.id  = hf.district_id
            WHERE dr.reported_date >= CURRENT_DATE - INTERVAL '180 days'
            ORDER BY d.name, dr.disease_name, dr.reported_date
            """
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _rule_tier_label(baseline_ratio: float, deaths: int) -> str:
    """Mirror backend.inference.outbreak_risk._rule_tier so the
    classifier learns the exact labels the rule engine emits."""
    if baseline_ratio >= 5.0 or deaths >= 3:
        return "Critical"
    if baseline_ratio >= 4.0 or deaths >= 1:
        return "High"
    if baseline_ratio >= 2.0:
        return "Medium"
    return "Low"


def _weekly_slope(series: list[int]) -> float:
    n = len(series)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(series) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, series))
    den = sum((x - mean_x) ** 2 for x in xs)
    return num / den if den else 0.0


def compute_features(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """Two clean passes: feature rows ordered, then a tiny post-pass
    attaching per-district z-scores over baseline ratios."""
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        by_key[(r["district_name"], r["disease_name"])].append(r)

    features: list[dict] = []
    labels: list[str] = []
    ratios_by_district: dict[str, list[float]] = defaultdict(list)

    for (_district, _disease), entries in by_key.items():
        entries.sort(key=lambda r: r["reported_date"])
        last_14 = entries[-14:]
        baseline_pool = entries[:-14] if len(entries) > 14 else entries
        baseline_pool = baseline_pool[-30:] or baseline_pool

        cases_last_14d = sum(int(e["case_count"] or 0) for e in last_14)
        deaths_last_14d = sum(int(e["deaths"] or 0) for e in last_14)
        if baseline_pool:
            baseline_avg = (
                sum(int(e["case_count"] or 0) for e in baseline_pool)
                / len(baseline_pool)
            )
        else:
            baseline_avg = 0.0
        baseline_ratio = (
            (cases_last_14d / 14.0) / baseline_avg if baseline_avg > 0 else 0.0
        )
        slope = _weekly_slope([int(e["case_count"] or 0) for e in last_14])

        features.append(
            {
                "cases_last_14d": cases_last_14d,
                "baseline_ratio": round(baseline_ratio, 4),
                "deaths_last_14d": deaths_last_14d,
                "weekly_trend_slope": round(slope, 4),
                "district_z": 0.0,  # filled in pass 2
                "_district": _district,
            }
        )
        labels.append(_rule_tier_label(baseline_ratio, deaths_last_14d))
        ratios_by_district[_district].append(baseline_ratio)

    # Pass 2: per-district z-scores, slotted back in original order.
    z_by_district: dict[str, list[float]] = {}
    for district, rs in ratios_by_district.items():
        if len(rs) >= 2:
            mu = statistics.mean(rs)
            sd = statistics.pstdev(rs) or 1.0
            z_by_district[district] = [(r - mu) / sd for r in rs]

    cursor: dict[str, int] = defaultdict(int)
    for f in features:
        district = f.pop("_district")
        zs = z_by_district.get(district, [])
        idx = cursor[district]
        f["district_z"] = round(
            float(zs[idx] if idx < len(zs) else 0.0), 4,
        )
        cursor[district] += 1

    return features, labels


def main() -> None:
    print("=" * 60)
    print("HMIS Outbreak Risk Classifier — Training")
    print("=" * 60)

    print("\n1. Connecting to PostgreSQL…")
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        rows = fetch_disease_reports(conn)
        if not rows:
            print("   No disease_reports found — skipping.")
            return
        print(f"   Loaded {len(rows)} disease_reports rows.")

        print("\n2. Computing per-(district, disease) feature rows…")
        features, labels = compute_features(rows)
        if not features:
            print("   Not enough history to compute features.")
            return
        print(f"   Built {len(features)} (district × disease) buckets.")
        dist = {t: labels.count(t) for t in ("Low", "Medium", "High", "Critical")}
        print("   Tier distribution:")
        for tier in ("Low", "Medium", "High", "Critical"):
            print(f"     {tier:>8}: {dist.get(tier, 0)}")

        print("\n3. Fitting DecisionTreeClassifier(max_depth=6, balanced, seed=42)…")
        # Imported lazily so the script works even when scikit-learn is
        # missing (e.g., a docs-only environment).
        from backend.ml.outbreak_classifier import OutbreakClassifier
        clf = OutbreakClassifier(max_depth=6, random_state=42)
        clf.fit(features, labels)

        print("\n4. Persisting model…")
        out_path = clf.save()
        size_kb = out_path.stat().st_size / 1024
        print(f"   Saved → {out_path}  ({size_kb:.1f} KB)")

        print("\n" + "=" * 60)
        print("Training complete. OutbreakRisk will load it on next boot.")
        print("=" * 60)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
