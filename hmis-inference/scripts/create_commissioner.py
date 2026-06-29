#!/usr/bin/env python3
"""Bootstrap the first COMMISSIONER. Idempotent.

Usage:
    python scripts/create_commissioner.py \
        --email commissioner@example.invalid \
        --password 'artem-dev-password' \
        --full-name 'Gujarat Health Commissioner'
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import asyncio
import psycopg2
import urllib.parse

DATABASE_URL = __import__("os").environ.get(
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--full-name", required=True)
    args = ap.parse_args()

    from backend.security import hash_password
    hashed = hash_password(args.password)

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (email, full_name, hashed_password, role)
                VALUES (%s, %s, %s, 'COMMISSIONER')
                ON CONFLICT (email) DO UPDATE
                SET full_name = EXCLUDED.full_name,
                    hashed_password = EXCLUDED.hashed_password,
                    role = 'COMMISSIONER',
                    is_active = TRUE
                """,
                (args.email.strip().lower(), args.full_name, hashed),
            )
        conn.commit()
        print(f"Commissioner ready: {args.email}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
