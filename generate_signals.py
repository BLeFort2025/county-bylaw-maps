import pandas as pd
import os
import datetime
import glob

# --- CONFIG ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SIGNALS_FILE = "signals/signals.csv"

def generate_signals():
    print("--- Generating Master Signal Map ---")
    
    # 1. Find all candidate files (V1 and V2)
    # Looks for candidates_minutes_*.csv AND candidates_selenium_*.csv
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
        print("ERROR: No candidate files found!")
        return

    print(f"Found {len(all_files)} source files:")
    for f in all_files:
        print(f" - {os.path.basename(f)}")

    # 2. Load and Merge
    dfs = []
    for f in all_files:
        try:
            dfs.append(pd.read_csv(f))
        except Exception as e:
            print(f"Skipping {f}: {e}")
            
    if not dfs:
        print("No data loaded.")
        return
        
    full_df = pd.concat(dfs, ignore_index=True)
    
    # Deduplicate (keep most recent if multiple hits for same muni)
    # Sort by date (descending) so we keep the latest
    if 'found_date' in full_df.columns:
        full_df = full_df.sort_values('found_date', ascending=False)
        
    initial_count = len(full_df)
    full_df = full_df.drop_duplicates(subset=['munid'], keep='first')
    deduped_count = len(full_df)
    
    print(f"\nMerged {initial_count} raw hits -> {deduped_count} unique municipality signals.")

    # 3. Transform to Map Format
    signals = pd.DataFrame()
    signals['munid'] = full_df['munid']
    signals['signal_type'] = 'scanner_hit'
    signals['meeting_date'] = datetime.date.today() # Placeholder
    signals['discovered_date'] = full_df['found_date']
    signals['topic'] = 'Potential DC Mention'
    
    # NEW: Pass through the trigger keyword
    if 'trigger_keyword' in full_df.columns:
        signals['trigger_keyword'] = full_df['trigger_keyword'].fillna('General Keyword')
    else:
        signals['trigger_keyword'] = 'General Keyword'
    
    # Clean up snippets
    if 'snippet' in full_df.columns:
        signals['snippet'] = full_df['snippet'].fillna("").astype(str).str.slice(0, 300).str.replace('\n', ' ') + "..."
    else:
        signals['snippet'] = "Keyword match detected."
        
    signals['evidence_url'] = full_df['found_url']
    signals['confidence'] = 0.8
    signals['review_status'] = 'needs_review' 

    # 4. Save
    output_path = os.path.join(SCRIPT_DIR, SIGNALS_FILE)
    if not os.path.exists(os.path.dirname(output_path)):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
    signals.to_csv(output_path, index=False)
    print(f"SUCCESS: Saved {len(signals)} signals to {SIGNALS_FILE}")
    print("------------------------------------------------")
    print("READY TO LAUNCH. Run 'python align_signals.py' next.")

if __name__ == "__main__":
    generate_signals()