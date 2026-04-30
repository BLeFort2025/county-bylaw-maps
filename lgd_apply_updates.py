"""
lgd_apply_updates.py — Apply Approved LGD Extractions to the Database

Reads the reviewed extraction CSV and applies approved updates to
bylaws.db with full audit logging.

Usage:
  python lgd_apply_updates.py                              # Use latest extraction CSV
  python lgd_apply_updates.py --csv path/to/reviewed.csv   # Use specific CSV
  python lgd_apply_updates.py --dry-run                    # Preview changes without writing
"""

import pandas as pd
import os
import sys
import sqlite3
import datetime
import argparse

if sys.platform == "win32":
    os.environ['PYTHONUNBUFFERED'] = '1'

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "bylaws.db")
SIGNALS_DIR = os.path.join(SCRIPT_DIR, "signals")


def log_audit(conn, table_name, record_id, field_name, old_value, new_value, user='gemini_batch'):
    """Write an entry to the audit_log table."""
    conn.execute("""
        INSERT INTO audit_log (timestamp, user_name, table_name, record_id, field_name, old_value, new_value)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.datetime.now().isoformat(),
        user, table_name, record_id, field_name,
        str(old_value) if old_value is not None else None,
        str(new_value) if new_value is not None else None,
    ))


def update_field(conn, table, record_id, field, old_val, new_val, dry_run=False):
    """Update a single field if the value has changed. Returns True if updated."""
    # Normalize for comparison
    old_str = str(old_val).strip() if old_val and str(old_val).strip() not in ('', 'None', 'nan', 'null') else ""
    new_str = str(new_val).strip() if new_val and str(new_val).strip() not in ('', 'None', 'nan', 'null') else ""

    if old_str == new_str:
        return False

    if not new_str:
        return False  # Don't clear existing data with empty values

    if dry_run:
        print(f"      WOULD UPDATE {table}.{field}: '{old_str[:60]}' -> '{new_str[:60]}'")
        return True

    conn.execute(f'UPDATE {table} SET "{field}" = ? WHERE id = ?', (new_str, record_id))
    log_audit(conn, table, record_id, field, old_str, new_str)
    return True


def main():
    parser = argparse.ArgumentParser(description="Apply LGD Extraction Updates to Database")
    parser.add_argument("--csv", type=str, default=None, help="Path to reviewed extraction CSV")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    print("=" * 70)
    print("  LGD DATABASE UPDATER")
    print(f"  Date: {datetime.date.today().isoformat()}")
    if args.dry_run:
        print("  MODE: DRY RUN (no changes will be written)")
    else:
        print("  MODE: LIVE (changes will be written to bylaws.db)")
    print("=" * 70)

    # ── Find CSV ──
    csv_path = args.csv
    if not csv_path:
        candidates = [f for f in os.listdir(SIGNALS_DIR)
                       if f.startswith("lgd_extraction_review_") and f.endswith(".csv")]
        if not candidates:
            print("ERROR: No extraction CSV found. Run lgd_batch_updater.py first.")
            return
        candidates.sort(reverse=True)
        csv_path = os.path.join(SIGNALS_DIR, candidates[0])

    print(f"  Loading: {csv_path}")
    df = pd.read_csv(csv_path)

    # Filter to successful extractions only
    success = df[df['Extraction Status'] == 'SUCCESS']
    failed = df[df['Extraction Status'] != 'SUCCESS']
    print(f"  Total rows: {len(df)}")
    print(f"  Successful extractions: {len(success)}")
    print(f"  Failed (skipping): {len(failed)}")

    if success.empty:
        print("  No successful extractions to apply.")
        return

    # ── Connect to database ──
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # ── Backup reminder ──
    if not args.dry_run:
        backup_name = f"bylaws_backup_{datetime.date.today().isoformat()}.db"
        backup_path = os.path.join(SCRIPT_DIR, backup_name)
        if not os.path.exists(backup_path):
            import shutil
            shutil.copy2(DB_PATH, backup_path)
            print(f"  Backup created: {backup_name}")
        else:
            print(f"  Backup exists: {backup_name}")

    print("-" * 70)

    # ── Process each municipality ──
    total_updates = 0
    munis_updated = 0

    for _, row in success.iterrows():
        muni_name = row['Municipality']
        bylaw_id = row.get('DB_bylaw_id')

        if pd.isna(bylaw_id) or not bylaw_id:
            # Look up bylaw_id from DB
            result = conn.execute("""
                SELECT b.id FROM bylaws b
                JOIN municipalities m ON m.id = b.municipality_id
                WHERE m.name = ? AND b.category = 'LGD'
            """, (muni_name,)).fetchone()
            if not result:
                print(f"  SKIP {muni_name} — not found in database")
                continue
            bylaw_id = result[0]
        else:
            bylaw_id = int(bylaw_id)

        # Get details_lgd id
        detail_row = conn.execute("SELECT id FROM details_lgd WHERE bylaw_id = ?", (bylaw_id,)).fetchone()
        if not detail_row:
            print(f"  SKIP {muni_name} — no details_lgd record (bylaw_id={bylaw_id})")
            continue
        detail_id = detail_row[0]

        print(f"\n  {muni_name} (bylaw_id={bylaw_id}, detail_id={detail_id}):")

        field_updates = 0

        # ── Update bylaws table ──
        bylaw_fields = {
            'bylaw_name': ('NEW_bylaw_name', 'OLD_bylaw_name'),
            'date_enacted': ('NEW_date_enacted', 'OLD_date_enacted'),
            'progress_label': ('NEW_progress_label', 'OLD_progress_label'),
        }

        for db_field, (new_col, old_col) in bylaw_fields.items():
            new_val = row.get(new_col)
            old_val = row.get(old_col)
            if update_field(conn, 'bylaws', bylaw_id, db_field, old_val, new_val, args.dry_run):
                field_updates += 1

        # Always update date_last_updated
        today = datetime.date.today().isoformat()
        if not args.dry_run:
            conn.execute("UPDATE bylaws SET date_last_updated = ? WHERE id = ?", (today, bylaw_id))
            log_audit(conn, 'bylaws', bylaw_id, 'date_last_updated', '', today)

        # ── Update details_lgd table ──
        lgd_fields = {
            'has_lgd_definition': ('NEW_has_lgd_definition', 'OLD_has_lgd_definition'),
            'lgd_definition': ('NEW_lgd_definition', 'OLD_lgd_definition'),
            'has_herding_def': ('NEW_has_herding_def', 'OLD_has_herding_def'),
            'herding_definition': ('NEW_herding_definition', 'OLD_herding_definition'),
            'exempt_license_fees': ('NEW_exempt_license_fees', 'OLD_exempt_license_fees'),
            'collar_tag_req': ('NEW_collar_tag_req', 'OLD_collar_tag_req'),
            'barking_restrictions': ('NEW_barking_restrictions', 'OLD_barking_restrictions'),
            'exempt_barking': ('NEW_exempt_barking', 'OLD_exempt_barking'),
            'dog_limit': ('NEW_dog_limit', 'OLD_dog_limit'),
        }

        for db_field, (new_col, old_col) in lgd_fields.items():
            new_val = row.get(new_col)
            old_val = row.get(old_col)
            if update_field(conn, 'details_lgd', detail_id, db_field, old_val, new_val, args.dry_run):
                field_updates += 1

        if field_updates > 0:
            munis_updated += 1
            total_updates += field_updates
            print(f"    -> {field_updates} field(s) updated")
        else:
            print(f"    -> No changes needed")

    # ── Commit ──
    if not args.dry_run:
        conn.commit()
        print(f"\n  COMMITTED all changes to {DB_PATH}")
    else:
        print(f"\n  DRY RUN complete — no changes written")

    conn.close()

    # ── Summary ──
    print("\n" + "=" * 70)
    print("  UPDATE SUMMARY")
    print(f"  Municipalities updated: {munis_updated}")
    print(f"  Total field changes:    {total_updates}")
    print(f"  date_last_updated set:  {munis_updated} records")
    print("=" * 70)


if __name__ == "__main__":
    main()
