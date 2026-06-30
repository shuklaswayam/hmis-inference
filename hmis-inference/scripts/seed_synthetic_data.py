#!/usr/bin/env python3
"""
Synthetic data generator for HMIS Inference System.

Generates 180 days of facility_metrics and disease_reports with
realistic patterns. Disease resolution: 12 distinct diseases ×
5 severity bands (mild / low / moderate / high / critical).

Output volume at full scale:
    180 days × 256 facilities × 12 diseases = ~552k disease_reports rows
    180 days × 256 facilities              = ~46k  facility_metrics rows
"""

import random
import sys
import os
from datetime import date, timedelta
from uuid import uuid4

import psycopg2
from psycopg2.extras import execute_values
import urllib.parse

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://hmis:hmis_password@localhost:5432/hmis")
parsed = urllib.parse.urlparse(DATABASE_URL)
DB_CONFIG = {
    "host": parsed.hostname or "localhost",
    "port": parsed.port or 5432,
    "database": parsed.path.lstrip("/") or "hmis",
    "user": parsed.username or "hmis",
    "password": parsed.password or "hmis_password",
}

# Disease catalogue — 12 distinct diseases spanning vector-borne,
# water-borne, respiratory, and vaccine-preventable categories.
# ``spike_window`` (start, end) sets the recent-14-day active spike so
# outbreak_risk sees above-baseline activity in the inference window.
# Each entry's structure matches the historical schema: a base daily
# case count plus optional monsoon seasonality and/or sporadic spikes.
DISEASES = {
    # Vector-borne (monsoon-driven)
    "Dengue":        {"base": 8,  "monsoon_multiplier": 4.0, "monsoon_weeks": (6, 8),
                      "spike_window": (165, 175)},
    "Malaria":       {"base": 3,  "monsoon_multiplier": 3.0, "monsoon_weeks": (6, 9),
                      "outbreak_days": [15, 42, 67, 110, 152, 168, 173]},
    "Chikungunya":   {"base": 2,  "monsoon_multiplier": 2.5, "monsoon_weeks": (7, 9),
                      "spike_window": (168, 178)},
    # Water-borne (monsoon and post-monsoon)
    "Diarrheal":     {"base": 5,  "monsoon_multiplier": 3.0, "monsoon_weeks": (5, 10),
                      "spike_window": (170, 178)},
    "Typhoid":       {"base": 2,  "monsoon_multiplier": 2.0, "monsoon_weeks": (6, 9)},
    "Cholera":       {"base": 1,  "monsoon_multiplier": 4.5, "monsoon_weeks": (7, 9),
                      "spike_window": (167, 176)},
    "Hepatitis_A":   {"base": 1,  "monsoon_multiplier": 3.0, "monsoon_weeks": (7, 10)},
    # Respiratory (winter + scattered)
    "Influenza":     {"base": 4,  "monsoon_multiplier": 2.0, "monsoon_weeks": (1, 5),
                      "spike_window": (172, 178)},
    "Pneumonia":     {"base": 3,  "monsoon_multiplier": 2.5, "monsoon_weeks": (1, 4),
                      "spike_window": (170, 177)},
    # Zoonotic / vector-borne (more dispersed)
    "Leptospirosis": {"base": 1,  "monsoon_multiplier": 5.0, "monsoon_weeks": (8, 10),
                      "spike_window": (167, 175)},
    # Vaccine-preventable (sporadic outbreaks)
    "Measles":       {"base": 1,  "outbreak_days": [22, 88, 144, 169, 174]},
    # Childhood respiratory — non-seasonal baseline with sparse spikes
    "Bronchitis":    {"base": 2,  "outbreak_days": [33, 95, 158, 170, 175]},
}

# 5 severity bands (mild < low < moderate < high < critical).
# Threshold mapping kept deterministic so downstream rule tiers in
# backend/inference/outbreak_risk.py see consistent labels.
SEVERITY_LEVELS = ["mild", "low", "moderate", "high", "critical"]

AGE_GROUPS = ["0-5", "5-15", "15-30", "30-45", "45-60", "60+"]
SEVERITY_LEVELS = ["mild", "low", "moderate", "high", "critical"]

HIGH_ICU_DAY = 34
HIGH_MATERNAL_DAY = 61
ICU_SPIKE_DAYS = {8, 22, 34, 55, 78, 110, 145, 168}
MILD_ICU_BUMP_DAYS = {12, 28, 41, 62, 95, 120, 155}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def get_facilities(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id, district_id, name FROM health_facilities")
        return cur.fetchall()


def generate_base_metrics(day_index: int, facility_seed: int) -> dict:
    rng = random.Random(facility_seed + day_index)
    day_of_week = day_index % 7
    weekend_factor = 0.6 if day_of_week >= 5 else 1.0
    # Trend spans the full 180-day window so a noticeable upward drift
    # is visible in the later weeks (mirrors post-monsoon uptick).
    trend = 1.0 + (day_index / 180.0) * 0.12

    base_opd = 200 * weekend_factor * trend
    opd_visits = max(10, int(base_opd + rng.gauss(0, base_opd * 0.2)))

    icu_base = 60.0
    if day_index in ICU_SPIKE_DAYS:
        icu_pct = rng.uniform(88.0, 98.0)
    elif day_index in MILD_ICU_BUMP_DAYS:
        icu_pct = rng.uniform(75.0, 88.0)
    else:
        icu_pct = max(10.0, min(95.0, icu_base + rng.gauss(0, 10)))

    bed_pct = max(30.0, min(100.0, 70.0 + rng.gauss(0, 8)))

    base_emergency = 40 * weekend_factor
    emergency_visits = max(5, int(base_emergency + rng.gauss(0, base_emergency * 0.15)))

    maternal_deaths = 0
    if day_index == HIGH_MATERNAL_DAY:
        maternal_deaths = 3
    elif rng.random() < 0.02:
        maternal_deaths = 1

    deliveries = max(2, int(10 * weekend_factor + rng.gauss(0, 3)))

    return {
        "opd_visits": opd_visits,
        "icu_occupancy_pct": round(icu_pct, 2),
        "bed_occupancy_pct": round(bed_pct, 2),
        "emergency_visits": emergency_visits,
        "maternal_deaths": maternal_deaths,
        "deliveries": deliveries,
    }


def generate_disease_cases(day_index: int, disease: str, config: dict, facility_seed: int) -> dict:
    rng = random.Random(facility_seed + day_index + hash(disease))

    cases = config["base"]

    if "monsoon_multiplier" in config and "monsoon_weeks" in config:
        week = day_index // 7 + 1
        start_w, end_w = config["monsoon_weeks"]
        if start_w <= week <= end_w:
            progress = (week - start_w) / (end_w - start_w)
            multiplier = 1.0 + (config["monsoon_multiplier"] - 1.0) * (1.0 - abs(2 * progress - 1))
            cases = int(cases * multiplier)

    if "outbreak_days" in config and day_index in config["outbreak_days"]:
        cases = cases * rng.randint(5, 8)

    # Recent-window spike so the outbreak_risk "last 14 days" comparison
    # has active case volume. Multiplier scales with the day-to-baseline
    # distance so a single bucket can span Low→Critical.
    if "spike_window" in config:
        s_start, s_end = config["spike_window"]
        if s_start <= day_index <= s_end:
            # Intensity peaks at the middle of the window so the
            # 14-day rolling sum has a meaningful crescendo.
            intensity = 1.0 - abs(day_index - (s_start + s_end) / 2.0) / max(1, (s_end - s_start) / 2.0)
            cases = int(cases * (3.0 + 4.0 * max(0.0, intensity)))
        elif day_index > (s_end + 1):
            # Post-spike decay: 2-3 days of elevated cases
            cases = int(cases * (1.5 + rng.uniform(0, 1.0)))

    noise = max(0, int(cases * rng.gauss(0, 0.25)))
    cases = max(0, cases + noise)

    if cases == 0:
        return None

    deaths = 0
    if cases > 10:
        death_rate = rng.uniform(0.01, 0.05)
        deaths = max(0, int(cases * death_rate))

    # 5-band severity mapping; the new "mild" band picks up the
    # very-low case-count days the old 4-band map was binning into
    # "low".
    if cases > 20:
        severity = "critical"
    elif cases > 12:
        severity = "high"
    elif cases > 6:
        severity = "moderate"
    elif cases > 2:
        severity = "low"
    else:
        severity = "mild"

    age_group = rng.choice(AGE_GROUPS)

    return {
        "case_count": cases,
        "deaths": deaths,
        "age_group": age_group,
        "severity": severity,
    }


def seed_metrics(conn, facilities, start_date: date, days: int = 180):
    print(f"Generating {days} days of facility_metrics for {len(facilities)} facilities...")
    rows = []
    for facility_idx, (facility_id, district_id, name) in enumerate(facilities):
        for day in range(days):
            current_date = start_date + timedelta(days=day)
            metrics = generate_base_metrics(day, facility_idx * 1000)
            rows.append((
                str(facility_id),
                current_date,
                metrics["opd_visits"],
                metrics["icu_occupancy_pct"],
                metrics["bed_occupancy_pct"],
                metrics["emergency_visits"],
                metrics["maternal_deaths"],
                metrics["deliveries"],
            ))

    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO facility_metrics (
                facility_id, reported_date, opd_visits, icu_occupancy_pct,
                bed_occupancy_pct, emergency_visits, maternal_deaths, deliveries
            )
            VALUES %s
            ON CONFLICT DO NOTHING
            """,
            rows,
            page_size=500,
        )
    conn.commit()
    print(f"  Inserted {len(rows)} facility_metrics rows")
    return len(rows)


def seed_disease_reports(conn, facilities, start_date: date, days: int = 180):
    print(f"Generating {days} days of disease_reports for {len(facilities)} facilities…")
    total_rows = 0
    all_rows = []

    for facility_idx, (facility_id, district_id, name) in enumerate(facilities):
        for day in range(days):
            current_date = start_date + timedelta(days=day)
            for disease_name, config in DISEASES.items():
                result = generate_disease_cases(day, disease_name, config, facility_idx * 1000)
                if result:
                    all_rows.append((
                        str(facility_id),
                        disease_name,
                        current_date,
                        result["case_count"],
                        result["deaths"],
                        result["age_group"],
                        result["severity"],
                    ))

    if all_rows:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO disease_reports (
                    facility_id, disease_name, reported_date, case_count,
                    deaths, age_group, severity
                )
                VALUES %s
                ON CONFLICT DO NOTHING
                """,
                all_rows,
                page_size=500,
            )
        conn.commit()
        total_rows = len(all_rows)

    print(f"  Inserted {total_rows} disease_reports rows")
    return total_rows


def verify_counts(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM facility_metrics")
        fm_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM disease_reports")
        dr_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM districts")
        d_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM health_facilities")
        hf_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM inference_results")
        ir_count = cur.fetchone()[0]

        cur.execute("SELECT MIN(reported_date), MAX(reported_date) FROM facility_metrics")
        date_range = cur.fetchone()

        cur.execute("""
            SELECT hf.name, COUNT(*)
            FROM disease_reports dr
            JOIN health_facilities hf ON hf.id = dr.facility_id
            GROUP BY hf.name
            ORDER BY hf.name
        """)
        per_facility = cur.fetchall()

        cur.execute("""
            SELECT disease_name, COUNT(*), SUM(case_count)
            FROM disease_reports
            GROUP BY disease_name
            ORDER BY disease_name
        """)
        per_disease = cur.fetchall()

        cur.execute("""
            SELECT severity, COUNT(*)
            FROM disease_reports
            GROUP BY severity
            ORDER BY severity
        """)
        per_severity = cur.fetchall()

    print("\n" + "=" * 60)
    print("SEED DATA VERIFICATION")
    print("=" * 60)
    print(f"Districts:            {d_count}")
    print(f"Health Facilities:    {hf_count}")
    print(f"Facility Metrics:     {fm_count} rows")
    print(f"Disease Reports:      {dr_count} rows")
    print(f"Inference Results:    {ir_count} rows")
    print(f"\nDate Range: {date_range[0]} to {date_range[1]}")

    print("\nDisease Reports per Facility:")
    for name, count in per_facility:
        print(f"  {name}: {count}")

    print("\nDisease Reports per Disease:")
    for name, count, total_cases in per_disease:
        print(f"  {name}: {count} reports, {total_cases} total cases")

    print("\nDisease Reports by Severity:")
    for severity, count in per_severity:
        print(f"  {severity}: {count}")

    print("=" * 60)


def main():
    conn = get_connection()
    try:
        facilities = get_facilities(conn)
        print(f"Found {len(facilities)} facilities")

        # Wipe the previous synthetic time-series so the expanded
        # dataset (180 days × 12 × 5) replaces it cleanly. We keep
        # districts, health_facilities, inference_results, and
        # inference_audit so downstream ranking still has alerts to
        # work with and the audit trail is not lost.
        print("Resetting facility_metrics + disease_reports (idempotent reload)…")
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE TABLE disease_reports, facility_metrics"
            )
        conn.commit()

        # 180-day rolling window ending today so inference lookbacks
        # (`CURRENT_DATE - INTERVAL '180 days'`) always have full coverage.
        end_date_excl = date.today()
        start_date = end_date_excl - timedelta(days=180)
        days = (end_date_excl - start_date).days
        print(f"Window: {start_date} → {end_date_excl} ({days} days)")

        fm_count = seed_metrics(conn, facilities, start_date, days=days)
        dr_count = seed_disease_reports(conn, facilities, start_date, days=days)

        total = fm_count + dr_count
        print(f"\nTotal rows inserted: {total}")

        verify_counts(conn)

    finally:
        conn.close()
        print("\nDone!")


if __name__ == "__main__":
    main()
