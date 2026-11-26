# -*- coding: utf-8 -*-
"""
migrate_site_alt_fees_schema.py — Idempotently add structured Site Alteration &
Excess Soil permit fee columns to details_site_alt in BOTH local SQLite (bylaws.db)
and Neon PostgreSQL, and initialize baseline audit statuses without touching any
existing exemption data.

Usage:
    python migrate_site_alt_fees_schema.py           # Local SQLite only
    python migrate_site_alt_fees_schema.py --cloud   # Local SQLite + Neon PostgreSQL DDL
"""

import argparse
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_DB = os.path.join(HERE, "bylaws.db")

NEW_COLUMNS = [
    ("fee_verification_status", "TEXT", "TEXT"),
    ("fee_year",                "INTEGER", "INTEGER"),
    ("fees_bylaw_name",         "TEXT", "TEXT"),
    ("fees_bylaw_link",         "TEXT", "TEXT"),
    ("ag_import_fee_status",    "TEXT", "TEXT"),
    ("ag_exempt_volume_cap_m3", "REAL", "DOUBLE PRECISION"),
    ("out_of_muni_fill_ban",    "TEXT", "TEXT"),
    ("fee_pricing_model",       "TEXT", "TEXT"),
    ("base_fee_small",          "REAL", "DOUBLE PRECISION"),
    ("base_fee_large",          "REAL", "DOUBLE PRECISION"),
    ("per_m3_rate",             "REAL", "DOUBLE PRECISION"),
    ("fee_calc_spec_json",      "TEXT", "TEXT"),
    ("est_fee_500_m3",          "REAL", "DOUBLE PRECISION"),
    ("est_fee_5000_m3",         "REAL", "DOUBLE PRECISION"),
    ("est_fee_15000_m3",        "REAL", "DOUBLE PRECISION"),
    ("security_deposit_terms",  "TEXT", "TEXT"),
    ("peer_review_recovery",    "TEXT", "TEXT"),
    ("fee_formula_notes",       "TEXT", "TEXT"),
]


def migrate_sqlite(db_path: str = LOCAL_DB) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    existing = {r[1] for r in cur.execute("PRAGMA table_info(details_site_alt)").fetchall()}
    added = []
    for col, sq_type, _ in NEW_COLUMNS:
        if col not in existing:
            cur.execute(f'ALTER TABLE details_site_alt ADD COLUMN "{col}" {sq_type}')
            added.append(col)

    # Initialize baseline statuses ONLY where fee_verification_status is currently NULL/blank
    cur.execute("""
        UPDATE details_site_alt
           SET fee_verification_status = 'N/A (No Bylaw)',
               ag_import_fee_status = COALESCE(ag_import_fee_status, 'No Bylaw')
         WHERE (fee_verification_status IS NULL OR TRIM(fee_verification_status) = '')
           AND bylaw_id IN (
               SELECT id FROM bylaws
                WHERE category = 'SITE_ALT'
                  AND (bylaw_name IS NULL OR TRIM(bylaw_name) = '')
           )
    """)
    no_bylaw_init = cur.rowcount

    cur.execute("""
        UPDATE details_site_alt
           SET fee_verification_status = 'Pending',
               ag_import_fee_status = COALESCE(ag_import_fee_status, 'Pending')
         WHERE (fee_verification_status IS NULL OR TRIM(fee_verification_status) = '')
           AND bylaw_id IN (
               SELECT id FROM bylaws
                WHERE category = 'SITE_ALT'
                  AND bylaw_name IS NOT NULL AND TRIM(bylaw_name) != ''
           )
    """)
    pending_init = cur.rowcount

    conn.commit()
    conn.close()
    print(f"[SQLite] Added {len(added)} column(s): {added}")
    print(f"[SQLite] Initialized {no_bylaw_init} 'N/A (No Bylaw)' rows and {pending_init} 'Pending' rows.")


def migrate_postgres() -> None:
    import psycopg2
    from db_utils import DEFAULT_NEON_URL

    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        secrets_path = os.path.join(HERE, ".streamlit", "secrets.toml")
        if os.path.exists(secrets_path):
            try:
                import tomllib
                with open(secrets_path, "rb") as fh:
                    url = str(tomllib.load(fh).get("DATABASE_URL", "")).strip()
            except Exception:
                pass
    url = url or DEFAULT_NEON_URL

    pconn = psycopg2.connect(url)
    pcur = pconn.cursor()
    try:
        for col, _, pg_type in NEW_COLUMNS:
            pcur.execute(
                f'ALTER TABLE "details_site_alt" ADD COLUMN IF NOT EXISTS "{col}" {pg_type}'
            )
        pconn.commit()
        print(f"[PostgreSQL] Ensured all {len(NEW_COLUMNS)} fee columns exist on details_site_alt.")
    except Exception:
        pconn.rollback()
        raise
    finally:
        pcur.close()
        pconn.close()


def main():
    parser = argparse.ArgumentParser(description="Add Site Alteration fee columns to details_site_alt")
    parser.add_argument("--cloud", action="store_true", help="Also run ALTER TABLE on Neon PostgreSQL")
    args = parser.parse_args()

    migrate_sqlite(LOCAL_DB)
    if args.cloud:
        migrate_postgres()


if __name__ == "__main__":
    main()
