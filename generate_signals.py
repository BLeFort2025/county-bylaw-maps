import pandas as pd
import os
import datetime
import glob
import sqlite3
from shared_config import (
    KEYWORD_CONFIG,
    canon_name,
    check_all_keywords,
    extract_snippet,
    extract_date_from_text,
    is_recent_date,
    is_stale_context,
    is_valid_meeting_document,
)

# --- CONFIG ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SIGNALS_FILE = "signals/signals.csv"
CACHE_FILE = os.path.join(SCRIPT_DIR, "signals", "cached_portal_docs.csv")
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


def _scan_cached_docs_for_signals() -> pd.DataFrame:
    """Scan signals/cached_portal_docs.csv for OFA bylaw category hits."""
    if not os.path.exists(CACHE_FILE):
        return pd.DataFrame()
    try:
        cdf = pd.read_csv(CACHE_FILE)
    except Exception:
        return pd.DataFrame()

    if cdf.empty:
        return pd.DataFrame()

    rows = []
    today_iso = datetime.date.today().isoformat()
    for _, r in cdf.iterrows():
        muni = str(r.get("municipality_name", "") or "").strip()
        text = str(r.get("doc_text", "") or "")
        url = str(r.get("doc_url", "") or "").strip()
        fdate = str(r.get("fetch_date", today_iso) or today_iso).strip()
        if fdate in ("", "nan", "None"):
            fdate = today_iso
        if not muni or len(text) < 50:
            continue
        u_dt = extract_date_from_text(url)
        if u_dt and not is_recent_date(u_dt, max_days=180):
            continue
        h_dt = extract_date_from_text(text[:600])
        if h_dt and not is_recent_date(h_dt, max_days=180):
            continue
        if not is_valid_meeting_document(url, text):
            continue
        for trigger, cat in check_all_keywords(text):
            rows.append({
                "munid": muni,
                "name": muni,
                "found_url": url,
                "found_date": fdate[:10],
                "snippet": extract_snippet(text, trigger, window=220),
                "trigger_keyword": trigger,
                "category": cat,
                "ai_summary": "",
                "ai_confidence": 0,
            })
    return pd.DataFrame(rows)


def generate_signals():
    print("--- Generating Master Signal Map (Smart Categorization + Cache Integration) ---")

    # 1. Find all candidate files (V1, V2, V3)
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

    dfs = []
    for f in all_files:
        try:
            df = pd.read_csv(f)
            if 'category' not in df.columns:
                df['category'] = 'DC'
            dfs.append(df)
        except Exception as e:
            print(f"Skipping {f}: {e}")

    # 2. Scan pre-fetched Selenium cache (cached_portal_docs.csv)
    cache_hits_df = _scan_cached_docs_for_signals()
    if not cache_hits_df.empty:
        print(f"Extracted {len(cache_hits_df)} raw category hits from cached_portal_docs.csv.")
        dfs.append(cache_hits_df)

    # 3. Also load existing signals from signals/signals.csv so historical/UI-saved signals are preserved
    output_path = os.path.join(SCRIPT_DIR, SIGNALS_FILE)
    if os.path.exists(output_path):
        try:
            old_sig = pd.read_csv(output_path)
            if not old_sig.empty:
                prev_df = pd.DataFrame({
                    "munid": old_sig["munid"],
                    "found_url": old_sig.get("evidence_url", ""),
                    "found_date": old_sig.get("discovered_date", ""),
                    "snippet": old_sig.get("snippet", ""),
                    "trigger_keyword": old_sig.get("trigger_keyword", ""),
                    "category": old_sig.get("category", "DC"),
                    "ai_summary": old_sig.get("ai_summary", ""),
                    "ai_confidence": old_sig.get("ai_confidence", 0),
                })
                dfs.append(prev_df)
        except Exception as e:
            print(f"Warning reading existing signals.csv: {e}")

    if not dfs:
        print("ERROR: No candidate files or cached hits found! Run the scanner first.")
        return

    full_df = pd.concat(dfs, ignore_index=True)
    full_df["canon_muni"] = full_df["munid"].apply(canon_name)
    full_df = full_df[full_df["canon_muni"] != ""].copy()

    # Filter out any invalid social media URLs
    full_df = full_df[
        full_df["found_url"].fillna("").apply(lambda u: is_valid_meeting_document(u))
    ].copy()

    # Filter out deprecated/removed trigger keywords from historical CSVs
    valid_keywords_upper = set()
    for kw_list in KEYWORD_CONFIG.values():
        for kw in kw_list:
            ku = kw.strip().upper()
            valid_keywords_upper.add(ku)
            valid_keywords_upper.add(ku.replace("BY-LAW", "BYLAW"))
            valid_keywords_upper.add(ku.replace("BYLAW", "BY-LAW"))
            valid_keywords_upper.add(ku.replace("BY-LAW", "BY LAW"))

    full_df = full_df[
        full_df["trigger_keyword"].fillna("").astype(str).str.strip().str.upper().isin(valid_keywords_upper)
    ].copy()
    full_df = full_df[
        ~full_df.apply(lambda r: is_stale_context(str(r.get("found_url", "")), "", str(r.get("snippet", "")) + " " + str(r.get("ai_summary", "")), max_days=180), axis=1)
    ].copy()

    # Prefer rows with AI summaries first, then newest found_date
    full_df["has_ai"] = full_df.get("ai_summary", pd.Series("", index=full_df.index)).fillna("").astype(str).str.strip().ne("")
    full_df["found_date"] = full_df["found_date"].fillna("").astype(str).str.slice(0, 10)
    full_df = full_df.sort_values(by=["has_ai", "found_date"], ascending=[False, False])

    # Deduplicate per (canonical municipality, category)
    full_df = full_df.drop_duplicates(subset=["canon_muni", "category"], keep="first")

    print(f"Merged {len(full_df)} unique (municipality, category) signals.")

    # 4. Transform to Map Format
    signals = pd.DataFrame()
    signals['munid'] = full_df['munid']
    signals['signal_type'] = 'scanner_hit'
    signals['discovered_date'] = full_df['found_date']
    signals['trigger_keyword'] = full_df.get('trigger_keyword', 'General Keyword')
    signals['category'] = full_df.get('category', 'DC')

    if 'snippet' in full_df.columns:
        signals['snippet'] = full_df['snippet'].fillna('').astype(str).replace('nan', '').str.slice(0, 350)
    else:
        signals['snippet'] = ''

    signals['ai_summary'] = full_df.get('ai_summary', '').fillna('').astype(str).replace('nan', '')

    if 'ai_confidence' in full_df.columns:
        signals['ai_confidence'] = pd.to_numeric(full_df['ai_confidence'], errors='coerce').fillna(0).astype(int)
    else:
        signals['ai_confidence'] = 0

    signals['evidence_url'] = full_df.get('found_url', '').fillna('').astype(str)

    # 5. Save CSV
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    signals.to_csv(output_path, index=False)
    print(f"SUCCESS: Saved {len(signals)} signals to {SIGNALS_FILE}")

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
