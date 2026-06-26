#!/usr/bin/env python3
"""
Seed script for HMIS Inference System.
Inserts 5 districts and 15 health facilities (3 per district) into PostgreSQL.
"""

import os
import uuid
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor

# Database configuration from environment
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://hmis:hmis_password@localhost:5432/hmis")
# Parse DATABASE_URL for psycopg2
import urllib.parse
parsed = urllib.parse.urlparse(DATABASE_URL)
DB_CONFIG = {
    "host": parsed.hostname or "localhost",
    "port": parsed.port or 5432,
    "database": parsed.path.lstrip("/") or "hmis",
    "user": parsed.username or "hmis",
    "password": parsed.password or "hmis_password",
}

DISTRICTS = [
    {
        "name": "Ahmedabad",
        "state": "Gujarat",
        "population": 8059441,
        "zone": "Central",
    },
    {
        "name": "Surat",
        "state": "Gujarat",
        "population": 6081322,
        "zone": "South",
    },
    {
        "name": "Vadodara",
        "state": "Gujarat",
        "population": 4165626,
        "zone": "Central",
    },
    {
        "name": "Rajkot",
        "state": "Gujarat",
        "population": 3804558,
        "zone": "Saurashtra",
    },
    {
        "name": "Bhavnagar",
        "state": "Gujarat",
        "population": 2880365,
        "zone": "Saurashtra",
    },
]

FACILITIES = {
    "Ahmedabad": [
        {
            "name": "Civil Hospital Ahmedabad",
            "facility_type": "District Hospital",
            "beds_total": 1200,
            "icu_beds": 80,
            "latitude": 23.0225,
            "longitude": 72.5714,
        },
        {
            "name": "VS Hospital",
            "facility_type": "Medical College Hospital",
            "beds_total": 800,
            "icu_beds": 60,
            "latitude": 23.0198,
            "longitude": 72.5824,
        },
        {
            "name": "LG Hospital",
            "facility_type": "General Hospital",
            "beds_total": 450,
            "icu_beds": 30,
            "latitude": 23.0341,
            "longitude": 72.5877,
        },
    ],
    "Surat": [
        {
            "name": "New Civil Hospital Surat",
            "facility_type": "District Hospital",
            "beds_total": 1000,
            "icu_beds": 70,
            "latitude": 21.1702,
            "longitude": 72.8311,
        },
        {
            "name": "SMIMER Hospital",
            "facility_type": "Medical College Hospital",
            "beds_total": 750,
            "icu_beds": 50,
            "latitude": 21.1959,
            "longitude": 72.8197,
        },
        {
            "name": "Surat Municipal Hospital",
            "facility_type": "General Hospital",
            "beds_total": 400,
            "icu_beds": 25,
            "latitude": 21.2048,
            "longitude": 72.8426,
        },
    ],
    "Vadodara": [
        {
            "name": "SSG Hospital",
            "facility_type": "Medical College Hospital",
            "beds_total": 900,
            "icu_beds": 65,
            "latitude": 22.3072,
            "longitude": 73.1812,
        },
        {
            "name": "GMERS Hospital Gotri",
            "facility_type": "District Hospital",
            "beds_total": 500,
            "icu_beds": 35,
            "latitude": 22.3245,
            "longitude": 73.1589,
        },
        {
            "name": "Vadodara General Hospital",
            "facility_type": "General Hospital",
            "beds_total": 300,
            "icu_beds": 20,
            "latitude": 22.2987,
            "longitude": 73.1923,
        },
    ],
    "Rajkot": [
        {
            "name": "Civil Hospital Rajkot",
            "facility_type": "District Hospital",
            "beds_total": 800,
            "icu_beds": 55,
            "latitude": 22.3039,
            "longitude": 70.8022,
        },
        {
            "name": "PDU Medical College Hospital",
            "facility_type": "Medical College Hospital",
            "beds_total": 700,
            "icu_beds": 45,
            "latitude": 22.2915,
            "longitude": 70.8078,
        },
        {
            "name": "Rajkot City Hospital",
            "facility_type": "General Hospital",
            "beds_total": 350,
            "icu_beds": 18,
            "latitude": 22.3098,
            "longitude": 70.7921,
        },
    ],
    "Bhavnagar": [
        {
            "name": "Sir T Hospital",
            "facility_type": "Medical College Hospital",
            "beds_total": 850,
            "icu_beds": 60,
            "latitude": 21.7645,
            "longitude": 72.1519,
        },
        {
            "name": "Civil Hospital Bhavnagar",
            "facility_type": "District Hospital",
            "beds_total": 500,
            "icu_beds": 30,
            "latitude": 21.7723,
            "longitude": 72.1487,
        },
        {
            "name": "Bhavnagar General Hospital",
            "facility_type": "General Hospital",
            "beds_total": 250,
            "icu_beds": 15,
            "latitude": 21.7589,
            "longitude": 72.1634,
        },
    ],
}


def get_connection():
    """Create and return a database connection."""
    return psycopg2.connect(**DB_CONFIG)


def seed_districts(conn):
    """Insert districts and return a mapping of district_name -> district_id."""
    district_ids = {}
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        for district in DISTRICTS:
            cur.execute(
                """
                INSERT INTO districts (name, state, population, zone)
                VALUES (%(name)s, %(state)s, %(population)s, %(zone)s)
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                district,
            )
            result = cur.fetchone()
            if result:
                district_ids[district["name"]] = result["id"]
                print(f"Inserted district: {district['name']} (ID: {result['id']})")
            else:
                # District already exists, fetch its ID
                cur.execute("SELECT id FROM districts WHERE name = %s", (district["name"],))
                existing = cur.fetchone()
                if existing:
                    district_ids[district["name"]] = existing["id"]
                    print(f"District already exists: {district['name']} (ID: {existing['id']})")
        conn.commit()
    return district_ids


def seed_facilities(conn, district_ids):
    """Insert health facilities for each district."""
    total_inserted = 0
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        for district_name, facilities in FACILITIES.items():
            district_id = district_ids.get(district_name)
            if not district_id:
                print(f"WARNING: District {district_name} not found, skipping facilities")
                continue

            for facility in facilities:
                cur.execute(
                    """
                    INSERT INTO health_facilities (
                        district_id, name, facility_type, beds_total, icu_beds,
                        latitude, longitude
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    RETURNING id
                    """,
                    (
                        district_id,
                        facility["name"],
                        facility["facility_type"],
                        facility["beds_total"],
                        facility["icu_beds"],
                        facility["latitude"],
                        facility["longitude"],
                    ),
                )
                result = cur.fetchone()
                if result:
                    total_inserted += 1
                    print(f"  Inserted facility: {facility['name']} (ID: {result['id']})")
                else:
                    print(f"  Facility already exists: {facility['name']}")
        conn.commit()
    return total_inserted


def verify_counts(conn):
    """Verify the inserted row counts."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT COUNT(*) as count FROM districts")
        districts_count = cur.fetchone()["count"]

        cur.execute("SELECT COUNT(*) as count FROM health_facilities")
        facilities_count = cur.fetchone()["count"]

        cur.execute(
            """
            SELECT d.name, COUNT(hf.id) as facility_count
            FROM districts d
            LEFT JOIN health_facilities hf ON d.id = hf.district_id
            GROUP BY d.id, d.name
            ORDER BY d.name
            """
        )
        per_district = cur.fetchall()

    print("\n=== Verification ===")
    print(f"Total districts: {districts_count}")
    print(f"Total facilities: {facilities_count}")
    print("\nFacilities per district:")
    for row in per_district:
        print(f"  {row['name']}: {row['facility_count']}")


def main():
    print("Connecting to database...")
    conn = get_connection()

    try:
        print("Seeding districts...")
        district_ids = seed_districts(conn)

        print("\nSeeding health facilities...")
        facilities_inserted = seed_facilities(conn, district_ids)

        print(f"\nInserted {facilities_inserted} new facilities")

        verify_counts(conn)

    finally:
        conn.close()
        print("\nDone!")


if __name__ == "__main__":
    main()