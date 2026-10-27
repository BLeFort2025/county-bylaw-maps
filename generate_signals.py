import pandas as pd
import os
import datetime
import glob
import sqlite3
from shared_config import canon_name

# --- CONFIG ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SIGNALS_FILE = "signals/signals.csv"
LOCAL_DB_PATH = os.path.join(SCRIPT_DIR, "bylaws.db")


def _build_muni_resolver(munis_df: pd.DataFrame):
    """Build exact and canonical municipality ID lookup dicts from a municipalities DataFrame."""
    exact_lookup = {}
    canon_lookup = {}
    for _, row in munis_df.iterrows():
        mid = int(row["id"])
        lk = str(row.get("lookup_key", "") or "").strip()
        nm = str(row.get("name", "") or "").strip()
        if lk:
            exact_lookup[lk] = mid
            exact_lookup[lk.upper()] = mid
            canon_lookup[canon_name(lk)] = mid
        if nm:
            exact_lookup[nm] = mid
            exact_lookup[nm.upper()] = mid
            canon_lookup[canon_name(nm)] = mid

    def resolve(raw_id: str):
        s = str(raw_id or "").strip()
        if not s:
            return None
        if s in exact_lookup:
            return exact_lookup[s]
        if s.upper() in exact_lookup:
            return exact_lookup[s.upper()]
        cn = canon_name(s)
        return canon_lookup.get(cn)

    return resolve


def generate_signals():
    print("--- Generating Master Signal Map (Smart Categorization) ---")
    
    # 1. Find all candidate files (V1 and V2)
    search_patterns = [
        os.path.join(SCRIPT_DIR, "signals", "candidates_minutes_*.csv"),
        os.path.join(SCRIPT_DIR, "signals", "candidates_selenium_*.csv"),
        os.path.join(SCRIPT_DIR, "signals", "v3_raw_hits_*.csv"),
        os.path.join(SCRIPT_DIR, "candidates_minutes_*.csv"),
        os.path.join(SCRIPT_DIR, "candidates_selenium_*.csv"),
        os.path.join(SCRIPT_DIR, "v3_raw_hits_*.csv")
    ]
    
    all_files = []
    for p in search_patterns:
        all_files.extend(glob.glob(p))
    
    if not all_files:
        print("ERROR: No candidate files found! Run the scanner first.")
        return

    print(f"Found {len(all_files)} source files.")

    # 2. Load and Merge
    dfs = []
    for f in all_files:
        try:
            df = pd.read_csv(f)
            # Ensure category column exists
            if 'category' not in df.columns:
                df['category'] = 'DC' # Default for old files
            dfs.append(df)
        except Exception as e:
            print(f"Skipping {f}: {e}")
            
    if not dfs:
        print("No valid data loaded.")
        return
        
    full_df = pd.concat(dfs, ignore_index=True)
    
    # Deduplicate (keep most recent hit per municipality)
    if 'found_date' in full_df.columns:
        full_df = full_df.sort_values('found_date', ascending=False)
        
    full_df = full_df.drop_duplicates(subset=['munid', 'category'], keep='first')
    
    print(f"Merged {len(full_df)} unique signals.")

    # 3. Transform to Map Format
    signals = pd.DataFrame()
    signals['munid'] = full_df['munid']
    signals['signal_type'] = 'scanner_hit'
    signals['discovered_date'] = full_df['found_date']
    
    # Pass through the new SMART columns
    signals['trigger_keyword'] = full_df.get('trigger_keyword', 'General Keyword')
    signals['category'] = full_df.get('category', 'DC') # <--- CRITICAL
    
    if 'snippet' in full_df.columns:
        signals['snippet'] = full_df['snippet'].astype(str).str.slice(0, 300)
    else:
        signals['snippet'] = ''
        
    signals['ai_summary'] = full_df.get('ai_summary', '')
    
    if 'ai_confidence' in full_df.columns:
        signals['ai_confidence'] = full_df['ai_confidence'].fillna(0).astype(int)
    else:
        signals['ai_confidence'] = 0
        
    signals['evidence_url'] = full_df.get('found_url', '')

    # 4. Save CSV
    output_path = os.path.join(SCRIPT_DIR, SIGNALS_FILE)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    signals.to_csv(output_path, index=False)
    print(f"SUCCESS: Saved signals to {SIGNALS_FILE}")

    # 5A. Sync to Local SQLite Database (bylaws.db)
    if os.path.exists(LOCAL_DB_PATH):
        try:
            sconn = sqlite3.connect(LOCAL_DB_PATH)
            scur = sconn.cursor()
            for col_def in [("ai_summary", "TEXT"), ("ai_confidence", "INTEGER")]:
                try:
                    scur.execute(f"ALTER TABLE scanner_signals ADD COLUMN {col_def[0]} {col_def[1]}")
                    sconn.commit()
                except Exception:
                    pass

            scur.execute("DELETE FROM scanner_signals")
            munis_local = pd.read_sql_query("SELECT id, lookup_key, name FROM municipalities", sconn)
            resolve_local = _build_muni_resolver(munis_local)

            local_rows = []
            matched_local = 0
            for _, s in signals.iterrows():
                raw_id = str(s.get("munid", ""))
                muni_id = resolve_local(raw_id)
                if muni_id is not None:
                    matched_local += 1
                ai_sum = str(s.get("ai_summary", "")) if pd.notna(s.get("ai_summary")) else ""
                ai_conf = int(s.get("ai_confidence", 0)) if pd.notna(s.get("ai_confidence")) else 0
                local_rows.append((
                    muni_id, raw_id, "scanner_hit", str(s.get("discovered_date", "")),
                    str(s.get("trigger_keyword", "")), str(s.get("category", "")),
                    str(s.get("snippet", "")), ai_sum, ai_conf, str(s.get("evidence_url", ""))
                ))

            scur.executemany("""
                INSERT INTO scanner_signals (
                    municipality_id, munid_raw, signal_type, discovered_date,
                    trigger_keyword, category, snippet, ai_summary, ai_confidence, evidence_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, local_rows)
            sconn.commit()
            sconn.close()
            print(f"SUCCESS: Synchronized {len(local_rows)} signals ({matched_local} linked to municipality_id) into local SQLite database.")
        except Exception as e:
            print(f"WARNING: Failed to sync to local SQLite database: {e}")

    # 5B. Sync to PostgreSQL Database (Neon) for the Streamlit App
    try:
        import psycopg2

        NEON_URL = os.environ.get(
            "DATABASE_URL",
            "postgresql://neondb_owner:npg_gjmiS41HEeXB@ep-fancy-resonance-amthrghm.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require"
        )
        conn = psycopg2.connect(NEON_URL)
        cursor = conn.cursor()

        for col_def in [
            ("ai_summary", "TEXT"),
            ("ai_confidence", "INTEGER"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE scanner_signals ADD COLUMN {col_def[0]} {col_def[1]}")
                conn.commit()
            except Exception:
                conn.rollback()

        cursor.execute("DELETE FROM scanner_signals")

        munis = pd.read_sql_query("SELECT id, lookup_key, name FROM municipalities", conn)
        resolve_pg = _build_muni_resolver(munis)

        rows_to_insert = []
        matched_pg = 0
        for _, s in signals.iterrows():
            raw_id = str(s.get("munid", ""))
            muni_id = resolve_pg(raw_id)
            if muni_id is not None:
                matched_pg += 1

            ai_sum = str(s.get("ai_summary", "")) if pd.notna(s.get("ai_summary")) else ""
            ai_conf = int(s.get("ai_confidence", 0)) if pd.notna(s.get("ai_confidence")) else 0

            rows_to_insert.append((
                muni_id, raw_id, "scanner_hit", str(s.get("discovered_date", "")),
                str(s.get("trigger_keyword", "")), str(s.get("category", "")),
                str(s.get("snippet", "")), ai_sum, ai_conf, str(s.get("evidence_url", ""))
            ))

        cursor.executemany("""
            INSERT INTO scanner_signals (
                municipality_id, munid_raw, signal_type, discovered_date,
                trigger_keyword, category, snippet, ai_summary, ai_confidence, evidence_url
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, rows_to_insert)

        conn.commit()
        conn.close()
        print(f"SUCCESS: Synchronized {len(rows_to_insert)} signals ({matched_pg} linked to municipality_id) into PostgreSQL database.")
    except Exception as e:
        print(f"WARNING: Failed to sync to PostgreSQL database: {e}")

if __name__ == "__main__":
    generate_signals()
