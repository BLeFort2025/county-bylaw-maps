# -*- coding: utf-8 -*-
"""
import_site_alt_fees_wave2.py — Ingest primary-source verified Wave 2 Site
Alteration & Excess Soil permit fee schedules (`wave2_site_alt_fees_verified.json`)
into local bylaws.db (SQLite) without altering any existing farm exemption
statuses, and export the updated OFA-branded QA workbook
(`wave1_site_alt_fees_qa.xlsx` / `province_wide_site_alt_fees_qa.xlsx`).

Usage:
    python import_site_alt_fees_wave2.py
"""

from __future__ import annotations

import datetime
import json
import os
import sqlite3

from import_site_alt_fees_wave1 import FEE_COLUMNS, export_qa_workbook, get_exemption_counts
from site_alt_fees_calc import compute_site_alt_benchmarks

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_DB = os.path.join(HERE, "bylaws.db")
WAVE2_JSON = os.path.join(HERE, "wave2_site_alt_fees_verified.json")


def ingest_wave2(conn: sqlite3.Connection) -> tuple[int, int]:
    cur = conn.cursor()
    before_counts = get_exemption_counts(cur)
    print("Baseline SITE_ALT farm_exemption counts:", before_counts)

    with open(WAVE2_JSON, "r", encoding="utf-8") as fh:
        records = json.load(fh)

    now_iso = datetime.datetime.now().isoformat(timespec="seconds")
    munis_updated = 0
    fields_updated = 0

    for rec in records:
        muni_name = rec["municipality"]
        fields = dict(rec["fields"])
        benchmarks = compute_site_alt_benchmarks(fields)
        fields.update(benchmarks)

        row = cur.execute(
            """
            SELECT d.id AS detail_id, b.id AS bylaw_id, m.name
            FROM municipalities m
            JOIN bylaws b ON b.municipality_id = m.id AND b.category = 'SITE_ALT'
            JOIN details_site_alt d ON d.bylaw_id = b.id
            WHERE LOWER(m.name) = LOWER(?)
            """,
            (muni_name,),
        ).fetchone()
        if not row:
            raise ValueError(f"Municipality not found in SITE_ALT details: {muni_name}")

        detail_id = row["detail_id"]
        old_row = dict(cur.execute("SELECT * FROM details_site_alt WHERE id = ?", (detail_id,)).fetchone())

        row_changes = 0
        for col in FEE_COLUMNS:
            if col not in fields:
                continue
            new_val = fields[col]
            old_val = old_row.get(col)
            if old_val != new_val:
                cur.execute(f'UPDATE details_site_alt SET "{col}" = ? WHERE id = ?', (new_val, detail_id))
                cur.execute(
                    """
                    INSERT INTO audit_log (timestamp, user_name, table_name, record_id, field_name, old_value, new_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now_iso,
                        "site_alt_fees_wave2",
                        "details_site_alt",
                        detail_id,
                        col,
                        str(old_val) if old_val is not None else None,
                        str(new_val) if new_val is not None else None,
                    ),
                )
                row_changes += 1
                fields_updated += 1

        if row_changes > 0:
            munis_updated += 1

    after_counts = get_exemption_counts(cur)
    assert before_counts == after_counts, f"Exemption counts changed! {before_counts} -> {after_counts}"
    conn.commit()
    print(f"Ingested {len(records)} Wave 2 records ({munis_updated} updated, {fields_updated} field writes).")
    print("Verified unchanged SITE_ALT farm_exemption counts:", after_counts)
    return munis_updated, fields_updated


def main() -> None:
    conn = sqlite3.connect(LOCAL_DB)
    conn.row_factory = sqlite3.Row
    try:
        ingest_wave2(conn)
        export_qa_workbook(
            conn,
            out_path=os.path.join(HERE, "province_wide_site_alt_fees_qa.xlsx"),
            title_label="OFA Municipal Site Alteration & Excess Topsoil Permit Fees — Complete Province-Wide QA Workbook (135/135)",
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
