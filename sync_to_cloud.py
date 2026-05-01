# -*- coding: utf-8 -*-
"""
sync_to_cloud.py — Push local bylaws.db (SQLite) to cloud PostgreSQL (Neon).

Strategy:
  - For data tables (municipalities, bylaws, bylaw_exemptions, details_*, contacts,
    lookup_values, provincial_acts, category_descriptions): FULL REPLACE via
    TRUNCATE + INSERT. The local SQLite is the source of truth.
  - For scanner_signals: UPSERT (merge) so we don't lose signals added via the live app.
  - For audit_log: APPEND only new entries (by timestamp).

Usage:
    python sync_to_cloud.py           # Dry run (shows what would change)
    python sync_to_cloud.py --push    # Actually push to cloud
"""

import os, sys, io, argparse, datetime
import sqlite3
import psycopg2
import psycopg2.extras

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_DB = os.path.join(HERE, "bylaws.db")
CLOUD_URL = 'postgresql://neondb_owner:npg_gjmiS41HEeXB@ep-fancy-resonance-amthrghm.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require'

# Tables to fully replace (order matters for foreign keys)
FULL_REPLACE_TABLES = [
    "municipalities",
    "bylaws",
    "bylaw_exemptions",
    "details_dc",
    "details_stormwater",
    "details_site_alt",
    "details_lgd",
    "details_trees",
    "details_chickens",
    "details_fences",
    "contacts",
    "lookup_values",
    "provincial_acts",
    "category_descriptions",
]


def log(msg):
    print(f"[SYNC] {msg}", flush=True)


def get_local_data(table):
    """Read all rows from a local SQLite table."""
    conn = sqlite3.connect(LOCAL_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f'SELECT * FROM [{table}]')
    rows = cur.fetchall()
    if rows:
        cols = rows[0].keys()
    else:
        cur.execute(f'PRAGMA table_info([{table}])')
        cols = [r[1] for r in cur.fetchall()]
    data = [dict(r) for r in rows]
    conn.close()
    return cols, data


def get_cloud_count(pcur, table):
    """Get row count from cloud table."""
    pcur.execute(f'SELECT COUNT(*) FROM "{table}"')
    return pcur.fetchone()[0]


def truncate_and_insert(pcur, table, cols, data, dry_run=True):
    """Truncate cloud table and insert all local rows."""
    cloud_count = get_cloud_count(pcur, table)
    local_count = len(data)
    
    log(f"  {table}: cloud={cloud_count}, local={local_count}")
    
    if dry_run:
        log(f"    [DRY RUN] Would TRUNCATE and INSERT {local_count} rows")
        return
    
    # Disable FK checks temporarily for the truncate cascade
    pcur.execute(f'TRUNCATE "{table}" CASCADE')
    
    if not data:
        return
    
    # Build INSERT statement
    col_names = [f'"{c}"' for c in cols]
    placeholders = ','.join(['%s'] * len(cols))
    sql = f'INSERT INTO "{table}" ({",".join(col_names)}) VALUES ({placeholders})'
    
    # Batch insert
    batch = []
    for row in data:
        values = tuple(row.get(c) for c in cols)
        batch.append(values)
    
    psycopg2.extras.execute_batch(pcur, sql, batch, page_size=100)
    log(f"    ✅ Inserted {len(batch)} rows")


def sync_scanner_signals(pcur, dry_run=True):
    """Merge scanner signals: insert local signals not in cloud."""
    cols, local_data = get_local_data("scanner_signals")
    cloud_count = get_cloud_count(pcur, "scanner_signals")
    
    log(f"  scanner_signals: cloud={cloud_count}, local={len(local_data)}")
    
    if dry_run:
        log(f"    [DRY RUN] Would merge scanner signals")
        return
    
    # Get existing IDs from cloud
    pcur.execute('SELECT id FROM scanner_signals')
    existing_ids = {r[0] for r in pcur.fetchall()}
    
    new_signals = [r for r in local_data if r['id'] not in existing_ids]
    
    if not new_signals:
        log(f"    No new signals to add")
        return
    
    col_names = [f'"{c}"' for c in cols]
    placeholders = ','.join(['%s'] * len(cols))
    sql = f'INSERT INTO scanner_signals ({",".join(col_names)}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING'
    
    batch = [tuple(r.get(c) for c in cols) for r in new_signals]
    psycopg2.extras.execute_batch(pcur, sql, batch)
    log(f"    ✅ Added {len(new_signals)} new signals")


def sync_audit_log(pcur, dry_run=True):
    """Append new audit log entries from local to cloud."""
    cols, local_data = get_local_data("audit_log")
    
    # Get max timestamp from cloud
    pcur.execute('SELECT MAX(timestamp) FROM audit_log')
    max_ts = pcur.fetchone()[0] or "2000-01-01"
    
    new_entries = [r for r in local_data if r.get('timestamp', '') > str(max_ts)]
    cloud_count = get_cloud_count(pcur, "audit_log")
    
    log(f"  audit_log: cloud={cloud_count}, local={len(local_data)}, new={len(new_entries)}")
    
    if dry_run:
        log(f"    [DRY RUN] Would append {len(new_entries)} new audit entries")
        return
    
    if not new_entries:
        log(f"    No new audit entries")
        return
    
    col_names = [f'"{c}"' for c in cols]
    placeholders = ','.join(['%s'] * len(cols))
    sql = f'INSERT INTO audit_log ({",".join(col_names)}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING'
    
    batch = [tuple(r.get(c) for c in cols) for r in new_entries]
    psycopg2.extras.execute_batch(pcur, sql, batch)
    log(f"    ✅ Appended {len(new_entries)} audit entries")


def reset_sequences(pcur):
    """Reset PostgreSQL sequences to match the max ID in each table."""
    tables_with_id = FULL_REPLACE_TABLES + ["scanner_signals", "audit_log"]
    for table in tables_with_id:
        try:
            pcur.execute(f'SELECT MAX(id) FROM "{table}"')
            max_id = pcur.fetchone()[0] or 0
            seq_name = f"{table}_id_seq"
            pcur.execute(f"SELECT setval('{seq_name}', {max_id + 1}, false)")
            log(f"  {table}: sequence reset to {max_id + 1}")
        except Exception as e:
            # Not all tables may have sequences
            pcur.connection.rollback()


def main():
    parser = argparse.ArgumentParser(description="Sync local bylaws.db to cloud PostgreSQL")
    parser.add_argument("--push", action="store_true", help="Actually push changes (default is dry run)")
    args = parser.parse_args()
    
    dry_run = not args.push
    
    print("=" * 70)
    print(f"  BYLAWS DATABASE SYNC — {'DRY RUN' if dry_run else '🚀 LIVE PUSH'}")
    print(f"  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Local: {LOCAL_DB}")
    print(f"  Cloud: Neon PostgreSQL")
    print("=" * 70)
    
    if not dry_run:
        confirm = input("\n⚠️  This will OVERWRITE cloud data with local data. Type 'YES' to confirm: ")
        if confirm.strip() != "YES":
            print("Aborted.")
            return
    
    # Connect to cloud
    pconn = psycopg2.connect(CLOUD_URL)
    pcur = pconn.cursor()
    
    try:
        # Phase 1: Full replace tables (disable FK checks via CASCADE)
        log("\n📦 Phase 1: Full table replacement...")
        
        # We need to handle FK dependencies. Truncate in reverse order,
        # then insert in forward order.
        reverse_tables = list(reversed(FULL_REPLACE_TABLES))
        
        if not dry_run:
            log("  Truncating tables (reverse FK order)...")
            for table in reverse_tables:
                pcur.execute(f'TRUNCATE "{table}" CASCADE')
                log(f"    Truncated {table}")
        
        for table in FULL_REPLACE_TABLES:
            cols, data = get_local_data(table)
            log(f"  {table}: {len(data)} rows")
            
            if not dry_run and data:
                col_names = [f'"{c}"' for c in cols]
                placeholders = ','.join(['%s'] * len(cols))
                sql = f'INSERT INTO "{table}" ({",".join(col_names)}) VALUES ({placeholders})'
                batch = [tuple(r.get(c) for c in cols) for r in data]
                psycopg2.extras.execute_batch(pcur, sql, batch, page_size=100)
                log(f"    ✅ Inserted {len(batch)} rows")
            elif dry_run:
                log(f"    [DRY RUN] Would replace with {len(data)} rows")
        
        # Phase 2: Merge scanner signals
        log("\n🔍 Phase 2: Scanner signals (merge)...")
        sync_scanner_signals(pcur, dry_run)
        
        # Phase 3: Append audit log
        log("\n📝 Phase 3: Audit log (append new)...")
        sync_audit_log(pcur, dry_run)
        
        # Phase 4: Reset sequences
        if not dry_run:
            log("\n🔄 Phase 4: Resetting sequences...")
            reset_sequences(pcur)
        
        if not dry_run:
            pconn.commit()
            log("\n✅ SYNC COMPLETE — All changes committed to cloud database.")
        else:
            pconn.rollback()
            log("\n📋 DRY RUN COMPLETE — No changes made. Run with --push to apply.")
        
    except Exception as e:
        pconn.rollback()
        log(f"\n❌ ERROR: {e}")
        raise
    finally:
        pcur.close()
        pconn.close()
    
    print("\n" + "=" * 70)
    print(f"  SYNC {'DRY RUN' if dry_run else 'PUSH'} FINISHED")
    print("=" * 70)


if __name__ == "__main__":
    main()
