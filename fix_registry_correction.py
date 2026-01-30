import pandas as pd
import os

# --- CONFIG ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SCRIPT_DIR, "signals", "portal_registry.csv")

# --- THE CORRECTION ---
# Correcting the "St. Clair/West Grey" copy-paste errors
FIXES = {
    "MARKSTAY WARREN M": "https://markstay-warren.civicweb.net/Portal/",
    "NORTHEASTERN MANITOULIN AND THE ISLANDS TP": "https://nemi.civicweb.net/Portal/",
    "PERTH EAST TP": "https://pertheast.civicweb.net/Portal/",
    "QUINTE WEST C": "https://quintewest.civicweb.net/Portal/",
    "ST. CLAIR TP": "https://stclair.civicweb.net/Portal/", # Confirming this one stays St. Clair
}

def apply_fixes():
    print(f"--- Registry Correction Tool ---")
    
    if not os.path.exists(REGISTRY_PATH):
        print(f"ERROR: Registry not found at {REGISTRY_PATH}")
        return

    try:
        df = pd.read_csv(REGISTRY_PATH)
    except Exception as e:
        print(f"Error reading registry: {e}")
        return
    
    fixed_count = 0
    
    for munid, new_url in FIXES.items():
        # EXACT MATCH ONLY to prevent bleed-over
        mask = df['munid'].astype(str).str.upper() == munid.upper()
        
        if mask.any():
            df.loc[mask, 'minutes_listing_url'] = new_url
            df.loc[mask, 'example_recent_minutes_url'] = new_url
            fixed_count += 1
            print(f"Corrected: {munid} -> {new_url}")

    if fixed_count > 0:
        df.to_csv(REGISTRY_PATH, index=False)
        print(f"\nSUCCESS: Corrected {fixed_count} entries.")
    else:
        print("\nNo changes made.")

if __name__ == "__main__":
    apply_fixes()