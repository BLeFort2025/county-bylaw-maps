import pandas as pd
import os
import datetime
import glob

# --- CONFIG ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SIGNALS_FILE = "signals/signals.csv"

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

    # 4. Save
    output_path = os.path.join(SCRIPT_DIR, SIGNALS_FILE)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    signals.to_csv(output_path, index=False)
    print(f"SUCCESS: Saved signals to {SIGNALS_FILE}")

    # 5. Sync to SQLite Database for the Streamlit App
    try:
        import sqlite3
        db_path = os.path.join(SCRIPT_DIR, "bylaws.db")
        conn = sqlite3.connect(db_path)
        
        # Ensure new AI columns exist
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(scanner_signals)")
        cols = [r[1] for r in cursor.fetchall()]
        if 'ai_summary' not in cols:
            conn.execute("ALTER TABLE scanner_signals ADD COLUMN ai_summary TEXT")
        if 'ai_confidence' not in cols:
            conn.execute("ALTER TABLE scanner_signals ADD COLUMN ai_confidence INTEGER")
            
        conn.execute("DELETE FROM scanner_signals")
        
        munis = pd.read_sql_query("SELECT id, lookup_key, name FROM municipalities", conn)
        muni_map = dict(zip(munis['lookup_key'], munis['id']))
        name_map = dict(zip(munis['name'], munis['id']))
        
        rows_to_insert = []
        for _, s in signals.iterrows():
            raw_id = str(s.get("munid", ""))
            muni_id = muni_map.get(raw_id)
            if not muni_id:
                muni_id = name_map.get(raw_id)
                
            ai_sum = str(s.get("ai_summary", ""))
            ai_conf = int(s.get("ai_confidence", 0)) if pd.notna(s.get("ai_confidence")) else 0
            
            rows_to_insert.append((
                muni_id, raw_id, "scanner_hit", str(s.get("discovered_date", "")),
                str(s.get("trigger_keyword", "")), str(s.get("category", "")),
                str(s.get("snippet", "")), ai_sum, ai_conf, str(s.get("evidence_url", ""))
            ))
            
        conn.executemany("""
            INSERT INTO scanner_signals (
                municipality_id, munid_raw, signal_type, discovered_date,
                trigger_keyword, category, snippet, ai_summary, ai_confidence, evidence_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows_to_insert)
        
        conn.commit()
        conn.close()
        print(f"SUCCESS: Synchronized {len(rows_to_insert)} signals into SQLite database.")
    except Exception as e:
        print(f"WARNING: Failed to sync to SQLite database: {e}")

if __name__ == "__main__":
    generate_signals()