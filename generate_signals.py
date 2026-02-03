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
        os.path.join(SCRIPT_DIR, "candidates_minutes_*.csv"),
        os.path.join(SCRIPT_DIR, "candidates_selenium_*.csv")
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
    signals['snippet'] = full_df.get('snippet', '').astype(str).str.slice(0, 300)
    signals['evidence_url'] = full_df.get('found_url', '')

    # 4. Save
    output_path = os.path.join(SCRIPT_DIR, SIGNALS_FILE)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    signals.to_csv(output_path, index=False)
    print(f"SUCCESS: Saved signals to {SIGNALS_FILE}")

if __name__ == "__main__":
    generate_signals()