import pandas as pd
import os

# CONFIG
MASTER_CSV = "Final_Bylaw_Data__Grouped_Correctly_.csv"
SIGNALS_CSV = "signals/signals.csv"

def align_signals():
    print("--- Aligning Signals to Master Data ---")
    
    # 1. Load Master Data (With Robust Encoding)
    if not os.path.exists(MASTER_CSV):
        print(f"ERROR: {MASTER_CSV} not found.")
        return
    
    # Try different encodings to handle special characters
    try:
        print("Attempting to read Master CSV (UTF-8)...")
        master_df = pd.read_csv(MASTER_CSV, encoding='utf-8')
    except UnicodeDecodeError:
        print("UTF-8 failed. Retrying with Windows-1252...")
        try:
            master_df = pd.read_csv(MASTER_CSV, encoding='cp1252')
        except UnicodeDecodeError:
            print("Windows-1252 failed. Retrying with Latin-1...")
            master_df = pd.read_csv(MASTER_CSV, encoding='latin1')

    # Check for the key column
    if 'Municipality' not in master_df.columns:
        print("ERROR: 'Municipality' column missing in Master CSV.")
        return
        
    master_names = master_df['Municipality'].dropna().unique()
    print(f"Loaded {len(master_names)} official municipality names from Master CSV.")

    # 2. Load Signals
    if not os.path.exists(SIGNALS_CSV):
        print(f"ERROR: {SIGNALS_CSV} not found.")
        return
        
    signals_df = pd.read_csv(SIGNALS_CSV)
    original_count = len(signals_df)
    
    # 3. Fuzzy Match Logic
    name_map = {}
    for name in master_names:
        # Create a "clean" version of the master name for matching
        clean = str(name).lower().replace(", tp", "").replace(", c", "").replace(", m", "").replace(", t", "").replace(", co", "").replace(", regional m", "").replace(", district m", "").strip()
        name_map[clean] = name
        name_map[str(name).lower().strip()] = name

    # Manual Overrides for tricky Upper Tier names
    overrides = {
        "chatham kent m": "Chatham-Kent, M",
        "durham": "Durham, Regional M",
        "hastings": "Hastings, Co",
        "lambton": "Lambton, Co",
        "lanark": "Lanark, Co",
        "muskoka": "Muskoka, District M",
        "niagara": "Niagara, Regional M"
    }
    
    updated_rows = 0
    
    for idx, row in signals_df.iterrows():
        current_val = str(row['munid']).strip()
        current_clean = current_val.lower().replace(" tp", "").replace(" c", "").replace(" m", "").replace(" t", "").strip()
        
        new_val = None
        if current_clean in overrides:
            new_val = overrides[current_clean]
        elif current_val.lower() in overrides: 
            new_val = overrides[current_val.lower()]
        elif current_clean in name_map:
            new_val = name_map[current_clean]
            
        if new_val:
            signals_df.at[idx, 'munid'] = new_val
            updated_rows += 1
        else:
            print(f"WARNING: Could not find Master CSV match for '{current_val}'")

    # 4. Save
    signals_df.to_csv(SIGNALS_CSV, index=False)
    print(f"\nSUCCESS: Aligned {updated_rows} out of {original_count} signals.")
    print(f"Saved to {SIGNALS_CSV}")

if __name__ == "__main__":
    align_signals()