#!/usr/bin/env python3
"""
Training script for the HMIS Anomaly Detection Model.
Loads 90-day historical data from PostgreSQL and trains an IsolationForest model.
"""

import os
import sys
import urllib.parse
from pathlib import Path

import joblib
import pandas as pd
import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.ml.anomaly import AnomalyDetector, FEATURES, MODEL_PATH


def _db_config() -> dict:
    """Parse DATABASE_URL like seed_data.py — works in compose, k8s, and local."""
    raw = os.environ.get(
        "DATABASE_URL",
        "postgresql://hmis:hmis_password@localhost:5432/hmis",
    )
    parsed = urllib.parse.urlparse(raw)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "database": (parsed.path or "/hmis").lstrip("/") or "hmis",
        "user": parsed.username or "hmis",
        "password": parsed.password or "hmis_password",
    }


DB_CONFIG = _db_config()


def load_training_data() -> pd.DataFrame:
    """Load 90-day historical data from PostgreSQL."""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        query = """
            SELECT
                fm.facility_id,
                fm.reported_date,
                fm.opd_visits,
                fm.icu_occupancy_pct,
                fm.bed_occupancy_pct,
                fm.emergency_visits,
                fm.maternal_deaths,
                fm.deliveries,
                COALESCE(SUM(dr.case_count), 0) as case_count
            FROM facility_metrics fm
            LEFT JOIN disease_reports dr
                ON dr.facility_id = fm.facility_id
                AND dr.reported_date = fm.reported_date
            GROUP BY fm.id, fm.facility_id, fm.reported_date,
                     fm.opd_visits, fm.icu_occupancy_pct, fm.bed_occupancy_pct,
                     fm.emergency_visits, fm.maternal_deaths, fm.deliveries
            ORDER BY fm.reported_date, fm.facility_id
        """
        df = pd.read_sql_query(query, conn)
        return df
    finally:
        conn.close()


def main():
    print("=" * 60)
    print("HMIS Anomaly Detection Model Training")
    print("=" * 60)

    print("\n1. Loading training data from PostgreSQL...")
    df = load_training_data()
    print(f"   Loaded {len(df)} rows from facility_metrics + disease_reports")
    print(f"   Date range: {df['reported_date'].min()} to {df['reported_date'].max()}")
    print(f"   Facilities: {df['facility_id'].nunique()}")

    print(f"\n2. Features used: {FEATURES}")
    for feat in FEATURES:
        print(f"   {feat}: mean={df[feat].mean():.2f}, std={df[feat].std():.2f}")

    print("\n3. Training IsolationForest...")
    detector = AnomalyDetector(
        contamination=0.1,
        random_state=42,
        n_estimators=100,
    )
    detector.fit(df)
    print("   Training complete.")

    print("\n4. Saving model...")
    model_path = detector.save()
    print(f"   Model saved to: {model_path}")
    print(f"   File size: {model_path.stat().st_size / 1024:.1f} KB")

    print("\n5. Quick validation scores:")
    test_normal = {
        "opd_visits": 200,
        "icu_occupancy_pct": 55.0,
        "case_count": 10,
        "emergency_visits": 30,
    }
    test_anomalous = {
        "opd_visits": 500,
        "icu_occupancy_pct": 98.0,
        "case_count": 200,
        "emergency_visits": 150,
    }
    normal_score = detector.score(test_normal)
    anomalous_score = detector.score(test_anomalous)
    print(f"   Normal data score:      {normal_score:.4f} (should be > 0)")
    print(f"   Anomalous data score:   {anomalous_score:.4f} (should be < 0)")

    print("\n" + "=" * 60)
    print("Training complete! Model ready for inference.")
    print("=" * 60)


if __name__ == "__main__":
    main()
